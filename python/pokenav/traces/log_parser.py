"""Trace records from a SerialPrograms log (the lab app's SerialPrograms.log).

Reads the controller commands the app queued (`issue_left_joystick()`,
`issue_buttons()`, ...) and the BDSP AutoStory walker's lines (`[Walk]`,
`[Route]`, `[Event]`, ...) and turns them into one record per input or walk.
See docs/TRACES.md for the record format.

The walker lines are the ones Arduino-Source's BDSP AutoStory logs since
commit dcc8778, which added `walk_until()` and `walk_route()`
(`PokemonBDSP_AutoStory_Walk.cpp`, `PokemonBDSP_AutoStory_RouteWalk.cpp`):
https://github.com/dayfine/Arduino-Source/commit/dcc877811742ed4c5ccd479841f79517c245640a
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, Iterable, List, Optional

from .common import (
    WALK_STOPS, button_input, dpad_input, format_time, new_record,
    parse_log_time, stick_input,
)

#  The walker's "still" threshold: a 400 ms slice that changes the screen by
#  less than this (RMSD at 192x108) did not move (PokemonBDSP_AutoStory_Walk.h).
PROGRAM_WALK_STILL = 10.0
#  walk_until() holds the stick in slices of this length.
PROGRAM_WALK_SLICE_MS = 400

_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) - \[([^\]]+)\]: (.*)$")

_JOYSTICK = re.compile(
    r"^issue_(left|right)_joystick\(\): \((-?[\d.]+),(-?[\d.]+)\), delay = (\d+)ms, hold = (\d+)ms"
)
_BUTTONS = re.compile(r"^issue_buttons\(\): ([^,]+), delay = (\d+)ms, hold = (\d+)ms")
_DPAD = re.compile(r"^issue_dpad\(\): (\w+), delay = (\d+)ms, hold = (\d+)ms")
_MASH = re.compile(r"^issue_mash_button\(\): ([^,]+), duration = (\d+)ms")
_NOP = re.compile(r"^issue_nop\(\): duration = (\d+)ms")

_STOPS = "|".join(WALK_STOPS)
_WALK_SLICE = re.compile(r"^\[Walk\] (.*): (\d+)ms, screen change (-?\d+(?:\.\d+)?)\.?$")
_WALK_END = re.compile(r"^\[Walk\] (.*): (" + _STOPS + r") after (\d+)ms, (\d+) wild battle\(s\)\.?$")
_WALK_FOR_END = re.compile(
    r"^\[Walk\] (.*): (" + _STOPS + r") after a (\d+)ms hold, (\d+) wild battle\(s\)\.?$")
_WALK_TAPS = re.compile(r"^\[Walk\] (.*): (\d+) taps\.?$")
_WALK_PROBE = re.compile(r"^\[Walk\] (.*): probe moved from (-?\d+)ms to (-?\d+)ms\.?$")
_TURNING = re.compile(r"^\[Route\] Turning (north|south|east|west)\.?$")

_PROGRAM_START = re.compile(r"^(?:<b>)?Starting Program: ([^<]+?)(?:</b>)?$")
_OBJECTIVE = re.compile(r"^\[AutoStory\] Objective: (.*)$")
_CHECKPOINT = re.compile(r"^\[Checkpoint\] (\S+): start")
_EVENT = re.compile(r"^\[Event\] (\S+ \S+): (start|done|failed.*)$")
_CFR_RUNNING = re.compile(r"^Command File Runner: running (.+)$")
_SCREENSHOT = re.compile(
    r"^(?:\[Checkpoint\] Screenshot|Failure screenshot|Save prompt screenshot): (.+\.(?:png|jpg))$")

_NOTE_TAGS = ("[Route]", "[Talk]", "[Sign]", "[Walk]")
_MAX_NOTES = 8
_MAX_NOTE_CHARS = 200


def _ms_between(a: _dt.datetime, b: _dt.datetime) -> int:
    return int(round((b - a).total_seconds() * 1000))


class LogParser:
    """Feed lines in order with feed(); call finish(); read `records`.

    Times: each input's `t` is when it should start on the console, from the
    log time of the line that queued it and the delays of the inputs queued
    before it (inputs queued together share one log time)."""

    def __init__(self, source_name: str = "SerialPrograms.log"):
        self.source_name = source_name
        self.records: List[Dict[str, Any]] = []
        #  Batch runs seen: (name, start time). Used to line up CFR .out files.
        self.batch_starts: List[tuple] = []
        self._reset_run(None, None)

    # -- context ------------------------------------------------------------

    def _reset_run(self, program: Optional[str], t: Optional[_dt.datetime]):
        self.program = program
        self.run_start = t
        self.objective = None
        self.checkpoint = None
        self.event = None
        self.batch = None
        self.batch_start = None
        self.sched: Optional[_dt.datetime] = None
        self.pending_turn = False
        self.taps_left = 0
        self.taps_run: Optional[Dict[str, Any]] = None
        self.walk: Optional[Dict[str, Any]] = None
        self.last_input: Optional[Dict[str, Any]] = None
        self.awaiting_shot: List[Dict[str, Any]] = []
        self.notes_target: Optional[Dict[str, Any]] = None
        self.run_counter = getattr(self, "run_counter", 0)

    def _new(self, kind: str, t: _dt.datetime) -> Dict[str, Any]:
        rec = new_record(kind, t, "cfr" if self.batch else "program")
        rec["program"] = self.program
        rec["run_start"] = format_time(self.run_start) if self.run_start else None
        rec["batch"] = self.batch
        rec["objective"] = self.objective
        rec["checkpoint"] = self.checkpoint
        rec["event"] = self.event
        if self.batch:
            rec["_batch_start"] = format_time(self.batch_start)
        return rec

    def _emit(self, rec: Dict[str, Any]):
        self.records.append(rec)
        self.awaiting_shot.append(rec)

    def _note(self, text: str):
        target = self.notes_target
        if target is None:
            return
        notes = target.setdefault("notes", None) or []
        if len(notes) < _MAX_NOTES:
            notes.append(text[:_MAX_NOTE_CHARS])
        target["notes"] = notes

    # -- lines --------------------------------------------------------------

    def feed_lines(self, lines: Iterable[str]):
        for line in lines:
            self.feed(line)

    def feed(self, line: str):
        m = _LINE.match(line.rstrip("\n"))
        if not m:
            return
        text = m.group(3)
        #  Cheap filter: almost every line is a watcher statistic.
        if not (text.startswith("issue_") or text.startswith("[") or "Program" in text
                or "screenshot" in text or text.startswith("Command File Runner")):
            return
        t = parse_log_time(m.group(1))

        if text.startswith("issue_"):
            self._on_input(t, text)
            return

        pm = _PROGRAM_START.match(text)
        if pm:
            self._close_walk(t, "unterminated")
            self._reset_run(pm.group(1).strip(), t)
            return
        if text.startswith("Program State: STOPPED"):
            self._close_walk(t, "unterminated")
            self.program = None
            self.batch = None
            return

        cm = _CFR_RUNNING.match(text)
        if cm:
            self._close_walk(t, "unterminated")
            self.batch = cm.group(1).strip()
            self.batch_start = t
            self.batch_starts.append((self.batch, t))
            self.sched = None
            return
        if text.startswith("Command File Runner: inbox is empty"):
            self.batch = None
            return

        sm = _SCREENSHOT.match(text)
        if sm:
            self._on_screenshot(t, sm.group(1))
            return

        om = _OBJECTIVE.match(text)
        if om:
            self.objective = om.group(1)
            return
        ckm = _CHECKPOINT.match(text)
        if ckm:
            self.checkpoint = ckm.group(1)
            return
        em = _EVENT.match(text)
        if em:
            if em.group(2) == "start":
                self.event = em.group(1)
            elif em.group(2).startswith("failed"):
                self._close_walk(t, "unterminated")
                self._note("[Event] " + em.group(1) + ": " + em.group(2))
            return

        if text.startswith("[Walk]"):
            self._on_walk_line(t, text)
            return
        tm = _TURNING.match(text)
        if tm:
            self.pending_turn = True
            self.notes_target = None
            return
        if text.startswith(_NOTE_TAGS):
            self._note(text)

    # -- inputs -------------------------------------------------------------

    def _schedule(self, t: _dt.datetime, delay_ms: int) -> _dt.datetime:
        start = t if self.sched is None or self.sched < t else self.sched
        self.sched = start + _dt.timedelta(milliseconds=delay_ms)
        return start

    def _on_input(self, t: _dt.datetime, text: str):
        jm = _JOYSTICK.match(text)
        if jm:
            side, x, y = jm.group(1), float(jm.group(2)), float(jm.group(3))
            delay, hold = int(jm.group(4)), int(jm.group(5))
            start = self._schedule(t, delay)
            inp = stick_input(x, y, hold, max(0, delay - hold), "L" if side == "left" else "R")
            self._on_stick(start, delay, inp)
            return
        bm = _BUTTONS.match(text)
        dm = _DPAD.match(text)
        mm = _MASH.match(text)
        if bm or dm or mm:
            if bm:
                delay, hold = int(bm.group(2)), int(bm.group(3))
                inp = button_input(bm.group(1).strip(), hold, max(0, delay - hold))
            elif dm:
                delay, hold = int(dm.group(2)), int(dm.group(3))
                inp = dpad_input(dm.group(1), hold, max(0, delay - hold))
            else:
                delay = int(mm.group(2))
                inp = button_input(mm.group(1).strip(), delay, 0)
                inp["mash"] = True
            start = self._schedule(t, delay)
            if self.walk is not None:
                #  Inside a walk: running from a wild battle. Counted, not kept.
                self.walk["_other_inputs"] += 1
                return
            rec = self._new("input", start)
            rec["t_end"] = format_time(start + _dt.timedelta(milliseconds=delay))
            rec["input"] = inp
            rec["role"] = "press"
            self._emit(rec)
            self.last_input = rec
            self.notes_target = rec
            return
        nm = _NOP.match(text)
        if nm:
            self._schedule(t, int(nm.group(1)))
            return
        #  Other commands (system scroll, raw controller state): time only.

    def _on_stick(self, start: _dt.datetime, delay: int, inp: Dict[str, Any]):
        end = start + _dt.timedelta(milliseconds=delay)
        if self.walk is not None:
            w = self.walk
            w["_slices_issued"] += 1
            w["_last_end"] = end
            return
        rec = self._new("input", start)
        rec["t_end"] = format_time(end)
        rec["input"] = inp
        rec["_start"] = start
        rec["_end"] = end
        if self.pending_turn:
            rec["role"] = "turn"
            self.pending_turn = False
        elif self.taps_left > 0:
            run = self.taps_run
            rec["role"] = "tap"
            rec["label"] = run["label"]
            rec["run"] = {"id": run["id"], "index": run["count"] - self.taps_left, "count": run["count"]}
            self.taps_left -= 1
        else:
            rec["role"] = "hold"
        self._emit(rec)
        self.last_input = rec
        self.notes_target = rec

    # -- walks --------------------------------------------------------------

    def _take_last_stick(self) -> Optional[Dict[str, Any]]:
        """The last input, if it is a stick hold not yet given a meaning, and
        removes it from the records (a walk's first slice)."""
        rec = self.last_input
        if rec is None or rec.get("kind") != "input" or rec["input"]["type"] != "stick":
            return None
        if rec["role"] not in ("hold",):
            return None
        if self.records and self.records[-1] is rec:
            self.records.pop()
            if rec in self.awaiting_shot:
                self.awaiting_shot.remove(rec)
            self.last_input = None
            return rec
        return None

    def _start_walk(self, t: _dt.datetime, label: str):
        first = self._take_last_stick()
        start = first["_start"] if first else t
        rec = self._new("walk", start)
        rec["label"] = label
        rec["role"] = "walk_until"
        rec["slice_ms"] = PROGRAM_WALK_SLICE_MS
        rec["still_threshold"] = PROGRAM_WALK_STILL
        rec["changes"] = []
        rec["wild_battles"] = 0
        if first:
            inp = dict(first["input"])
            inp.pop("hold_ms", None)
            inp.pop("release_ms", None)
            rec["input"] = inp
        rec["_slices_issued"] = 1 if first else 0
        rec["_slice_ms_at"] = []
        rec["_other_inputs"] = 0
        rec["_last_end"] = first["_end"] if first else t
        rec["_start"] = start
        self.walk = rec

    def _close_walk(self, t: _dt.datetime, outcome: str, total_ms: Optional[int] = None,
                    wild_battles: Optional[int] = None):
        w = self.walk
        if w is None:
            return
        self.walk = None
        w["outcome"] = outcome
        at = w.pop("_slice_ms_at")
        changes = w["changes"]
        if total_ms is None:
            total_ms = at[-1] if at else None
        w["total_ms"] = total_ms
        moving = 0
        for ms, c in zip(at, changes):
            if c >= PROGRAM_WALK_STILL:
                moving = ms
        w["moving_ms"] = moving if at else None
        if wild_battles is not None:
            w["wild_battles"] = wild_battles
        end = w.pop("_last_end")
        w["t_end"] = format_time(max(end, t) if outcome != "unterminated" else end)
        w.pop("_slices_issued", None)
        other = w.pop("_other_inputs", 0)
        if other:
            w["battle_inputs"] = other
        self._emit(w)
        self.last_input = w
        self.notes_target = w

    def _on_walk_line(self, t: _dt.datetime, text: str):
        m = _WALK_SLICE.match(text)
        if m:
            label, ms, change = m.group(1), int(m.group(2)), float(m.group(3))
            if self.walk is not None and self.walk["label"] != label:
                self._close_walk(t, "unterminated")
            if self.walk is None:
                self._start_walk(t, label)
            self.walk["changes"].append(round(change, 2))
            self.walk["_slice_ms_at"].append(ms)
            return
        m = _WALK_END.match(text)
        if m:
            label, stop, ms, wb = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
            if self.walk is None and ms > 0:
                self._start_walk(t, label)
            if self.walk is not None:
                self._close_walk(t, stop, ms, wb)
            return
        m = _WALK_FOR_END.match(text)
        if m:
            label, stop, ms, wb = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
            rec = self.last_input
            if rec is not None and rec.get("kind") == "input" and rec["input"]["type"] == "stick" \
                    and rec["role"] == "hold" and rec["input"]["hold_ms"] == ms:
                rec["role"] = "walk_for"
                rec["label"] = label
                rec["outcome"] = stop
                rec["total_ms"] = ms
                rec["wild_battles"] = wb
            return
        m = _WALK_TAPS.match(text)
        if m:
            label, count = m.group(1), int(m.group(2))
            self.taps_left = count
            self.taps_run = {"id": format_time(t), "label": label, "count": count}
            self.notes_target = None
            return
        m = _WALK_PROBE.match(text)
        if m:
            rec = self.last_input
            if rec is not None and rec.get("kind") == "input" and rec["input"]["type"] == "stick":
                rec["role"] = "probe"
                rec["label"] = m.group(1)
                rec["probe_first_move_ms"] = int(m.group(2))
                rec["probe_last_move_ms"] = int(m.group(3))
            return
        if self.walk is not None:
            if "wild battle" in text:
                self.walk.setdefault("notes", None)
                self.walk["notes"] = (self.walk["notes"] or []) + [text[:_MAX_NOTE_CHARS]]
            return
        self._note(text)

    # -- screenshots --------------------------------------------------------

    def _on_screenshot(self, t: _dt.datetime, path: str):
        for rec in self.awaiting_shot:
            if rec.get("screenshot") is None:
                rec["screenshot"] = path
                end = _dt.datetime.strptime(rec["t_end"] or rec["t"], "%Y-%m-%dT%H:%M:%S.%f")
                rec["screenshot_after_ms"] = max(0, _ms_between(end, t))
        self.awaiting_shot = []

    # -- end ----------------------------------------------------------------

    def finish(self):
        if self.walk is not None:
            w = self.walk
            self._close_walk(w["_last_end"], "unterminated")
        for rec in self.records:
            rec.pop("_start", None)
            rec.pop("_end", None)


def parse_log(path: str) -> LogParser:
    parser = LogParser(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        parser.feed_lines(f)
    parser.finish()
    return parser
