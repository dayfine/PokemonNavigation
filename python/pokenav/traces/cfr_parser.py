"""Trace records from Command File Runner result files (`outbox/<name>.out`).

A result file lists each command with its offsets from the start of the
batch (`ok 3 stick L -1 0 200 600 @4794-5595ms`), preceded by what the command
printed (`walk still after 4400ms, moving 4000ms; changes 3 52 ...`;
`shot <path>` lines, screenshots on the lab Mac, are skipped). The batch's start time comes from the lab log's
`Command File Runner: running <name>` line when there is one, else from the
file's modification time.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .common import button_input, dpad_input, format_time, new_record, stick_input

#  Command File Runner defaults (CommandFileRunner README).
STICK_DEFAULT = (160, 160)
PRESS_DEFAULT = (160, 160)
DPAD_DEFAULT = (100, 200)
WALK_DEFAULT_MAX = 5000
WALK_DEFAULT_STILL = 10.0
WALK_SLICE_MS = 200

#  A run of taps: consecutive same-direction stick holds this long.
TAP_MIN_MS = 100
TAP_MAX_MS = 300

_OK = re.compile(r"^ok (\d+) (.*) @(\d+)-(\d+)ms$")
_ERROR = re.compile(r"^error line (\d+) \((.*)\): (.*)$")
_WALK_OUT = re.compile(r"^walk (still|limit) after (\d+)ms, moving (\d+)ms; changes ?(.*)$")
_SHOT = re.compile(r"^shot (.+)$")


def _opt_int(words: Sequence[str], i: int, default: int) -> int:
    if len(words) > i:
        return int(round(float(words[i])))
    return default


def _opt_float(words: Sequence[str], i: int, default: float) -> float:
    if len(words) > i:
        return float(words[i])
    return default


def _strip_comment(command: str) -> str:
    return command.split("#", 1)[0].strip()


def parse_out_text(text: str, name: str, start: _dt.datetime, time_source: str) -> List[Dict[str, Any]]:
    """Records for one batch whose first command started at `start`."""
    records: List[Dict[str, Any]] = []
    printed: List[str] = []
    last_controller: Optional[Dict[str, Any]] = None

    def at(ms: int) -> _dt.datetime:
        return start + _dt.timedelta(milliseconds=ms)

    def base(kind: str, line_no: int, command: str, t0: int, t1: int) -> Dict[str, Any]:
        rec = new_record(kind, at(t0), "cfr")
        rec["t_end"] = format_time(at(t1))
        rec["program"] = "NintendoSwitch:CommandFileRunner"
        rec["batch"] = name
        rec["run_start"] = format_time(start)
        rec["line"] = line_no
        rec["command"] = command
        rec["time_source"] = time_source
        return rec

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line == "end":
            continue
        ok = _OK.match(line)
        err = None if ok else _ERROR.match(line)
        if not ok and not err:
            printed.append(line)
            continue
        if ok:
            line_no, command, t0, t1 = int(ok.group(1)), ok.group(2), int(ok.group(3)), int(ok.group(4))
        else:
            line_no, command, t0, t1 = int(err.group(1)), err.group(2), None, None
        out, printed = printed, []
        others = [o for o in out if not _SHOT.match(o)]
        words = _strip_comment(command).split()
        if not words:
            continue
        verb = words[0]
        if err:
            #  The failing line: no times. Mark the last controller record.
            if last_controller is not None:
                notes = last_controller["notes"] or []
                notes.append("next line failed: " + line)
                last_controller["notes"] = notes
            continue

        rec = None
        try:
            if verb == "stick":
                side = words[1] if len(words) > 1 else "L"
                x, y = _opt_float(words, 2, 0.0), _opt_float(words, 3, 0.0)
                hold = _opt_int(words, 4, STICK_DEFAULT[0])
                release = _opt_int(words, 5, STICK_DEFAULT[1])
                rec = base("input", line_no, command, t0, t1)
                rec["input"] = stick_input(x, y, hold, release, side.upper())
                rec["role"] = "hold"
            elif verb == "press":
                rec = base("input", line_no, command, t0, t1)
                rec["input"] = button_input(words[1], _opt_int(words, 2, PRESS_DEFAULT[0]),
                                            _opt_int(words, 3, PRESS_DEFAULT[1]))
                rec["role"] = "press"
            elif verb == "dpad":
                rec = base("input", line_no, command, t0, t1)
                rec["input"] = dpad_input(words[1], _opt_int(words, 2, DPAD_DEFAULT[0]),
                                          _opt_int(words, 3, DPAD_DEFAULT[1]))
                rec["role"] = "press"
            elif verb == "walk":
                x, y = _opt_float(words, 1, 0.0), _opt_float(words, 2, 0.0)
                rec = base("walk", line_no, command, t0, t1)
                inp = stick_input(x, y, None, None)
                rec["input"] = inp
                rec["role"] = "cfr_walk"
                rec["walk_max_ms"] = _opt_int(words, 3, WALK_DEFAULT_MAX)
                rec["still_threshold"] = _opt_float(words, 4, WALK_DEFAULT_STILL)
                rec["slice_ms"] = WALK_SLICE_MS
                for o in others:
                    wm = _WALK_OUT.match(o)
                    if wm:
                        rec["outcome"] = wm.group(1)
                        rec["total_ms"] = int(wm.group(2))
                        rec["moving_ms"] = int(wm.group(3))
                        rec["changes"] = [int(c) for c in wm.group(4).split()]
                others = [o for o in others if not _WALK_OUT.match(o)]
        except (IndexError, ValueError):
            rec = None

        if rec is not None:
            if others:
                rec["notes"] = [o[:200] for o in others[:8]]
            records.append(rec)
            last_controller = rec

    _mark_tap_runs(records)
    return records


def _mark_tap_runs(records: List[Dict[str, Any]]):
    """Consecutive commands that are left-stick holds of TAP_MIN_MS..TAP_MAX_MS
    toward one direction become a tap run (role 'tap')."""
    def tap_key(rec):
        inp = rec.get("input") or {}
        if rec["kind"] != "input" or inp.get("type") != "stick" or inp.get("stick") != "L":
            return None
        if not (TAP_MIN_MS <= (inp.get("hold_ms") or 0) <= TAP_MAX_MS):
            return None
        return (inp["x"], inp["y"])

    i = 0
    while i < len(records):
        key = tap_key(records[i])
        j = i
        if key is not None:
            while j + 1 < len(records) and tap_key(records[j + 1]) == key \
                    and records[j + 1]["line"] == records[j]["line"] + 1:
                j += 1
        if key is not None and j > i:
            run_id = "%s:%d" % (records[i]["batch"], records[i]["line"])
            for k in range(i, j + 1):
                records[k]["role"] = "tap"
                records[k]["run"] = {"id": run_id, "index": k - i, "count": j - i + 1}
        i = j + 1


def batch_start_for(name: str, mtime: _dt.datetime,
                    batch_starts: Sequence[Tuple[str, _dt.datetime]]) -> Optional[_dt.datetime]:
    """The last 'running <name>' at or before the file was written."""
    best = None
    for n, t in batch_starts:
        if n == name and t <= mtime + _dt.timedelta(seconds=5):
            if best is None or t > best:
                best = t
    return best


def parse_out_file(path: str, batch_starts: Sequence[Tuple[str, _dt.datetime]] = ()) -> List[Dict[str, Any]]:
    name = os.path.basename(path)
    if name.endswith(".out"):
        name = name[:-4]
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    mtime = _dt.datetime.fromtimestamp(os.path.getmtime(path))
    start = batch_start_for(name, mtime, batch_starts)
    source = "log"
    if start is None or (mtime - start) > _dt.timedelta(hours=2):
        #  No log line: the file is written when the batch ends.
        last = 0
        for m in map(_OK.match, text.splitlines()):
            if m:
                last = max(last, int(m.group(4)))
        start = mtime - _dt.timedelta(milliseconds=last)
        source = "mtime"
    return parse_out_text(text, name, start, source)


def list_out_files(directory: str) -> List[str]:
    if not os.path.isdir(directory):
        return []
    return sorted(os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".out"))
