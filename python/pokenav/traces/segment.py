"""Split a trace into segments, one file each, named by what was being done.

A unit is one program run (`run_start`) or one CFR batch (`batch` +
`run_start`). Units fall into series:

- story: AutoStory runs, keyed by the objective they started from, plus the
  CFR batches that set them up (`r<N>...` batches such as `r163a-load`);
- cfr: other CFR batches (walking by hand, probing, menus), keyed by the
  objective of the next AutoStory run, else of the run before;
- idle: other programs (PreventSleep) and `keepawake` CFR batches.

A series is cut into segments where a unit starts more than GAP after the
previous unit of the series ended, and at midnight. Segments of different
series may overlap in time (two panels in one profile).
"""

from __future__ import annotations

import datetime as _dt
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

GAP = _dt.timedelta(minutes=45)
AUTOSTORY = "AutoStory"

_SETUP_BATCH = re.compile(r"^r\d+[a-z]?-")
_IDLE_BATCH = re.compile(r"^keepawake")
_TAG = re.compile(r"^[a-z]+\d*")
_OBJECTIVE_ID = re.compile(r"^(\d+)\.(\d+[a-z]?)\b\s*(?:-\s*)?")


def _parse_t(t: str) -> _dt.datetime:
    return _dt.datetime.strptime(t, "%Y-%m-%dT%H:%M:%S.%f")


def _slug(text: str, words: int = 4) -> str:
    parts = re.findall(r"[a-z0-9]+", text.lower().replace("poké", "poke"))
    return "-".join(parts[:words])


def objective_slug(objective: Optional[str]) -> str:
    """'00.05f Jubilife: the clown by ...' -> '0005f'; '00.04 - After
    Pokedex (after ...). Ends: ...' -> '0004-after-pokedex' (only used when
    a run has no checkpoints); 'Route 202 to Sandgem's ...' -> 'route-202-to-sandgem'."""
    if not objective:
        return ""
    m = _OBJECTIVE_ID.match(objective)
    if m:
        return m.group(1) + m.group(2)
    return _slug(re.split(r"[.(]", objective)[0])


def _objective_text(objective: Optional[str]) -> str:
    if not objective:
        return ""
    m = _OBJECTIVE_ID.match(objective)
    rest = objective[m.end():] if m else objective
    return _slug(re.split(r"[.(]", rest)[0])


def batch_tag(batch: str) -> str:
    """'r163a-load' -> 'r163', 'm158-w1' -> 'm158', 'x10' -> 'x10', 'del-3' -> 'del'."""
    m = _TAG.match(batch.lower())
    tag = m.group() if m else batch
    if _SETUP_BATCH.match(batch):
        tag = re.match(r"r\d+", batch).group()
    return tag


class _Unit:
    def __init__(self, records: List[Dict[str, Any]]):
        self.records = records
        first = records[0]
        self.start = _parse_t(first.get("run_start") or first["t"])
        self.end = max(_parse_t(r["t"]) for r in records)
        self.batch = first.get("batch")
        program = first.get("program") or ""
        if first["source"] == "cfr":
            if _IDLE_BATCH.match(self.batch or ""):
                self.series = "idle"
            elif _SETUP_BATCH.match(self.batch or ""):
                self.series = "story"
            else:
                self.series = "cfr"
        elif program.endswith(":" + AUTOSTORY):
            self.series = "story"
        else:
            self.series = "idle"
        self.is_run = first["source"] == "program" and self.series == "story"
        self.objective = next((r["objective"] for r in records if r.get("objective")), None)
        self.checkpoints = []  # type: List[str]
        for r in records:
            cp = r.get("checkpoint")
            if cp and cp not in self.checkpoints:
                self.checkpoints.append(cp)
        self.topic = objective_slug(self.objective) if self.is_run else None


def _units(records: List[Dict[str, Any]]) -> List[_Unit]:
    groups = OrderedDict()  # type: Dict[Tuple, List[Dict[str, Any]]]
    for r in records:
        if r["source"] == "cfr":
            key = ("cfr", r.get("batch"), r.get("run_start"))
        else:
            key = ("program", r.get("program"), r.get("run_start"))
        groups.setdefault(key, []).append(r)
    units = [_Unit(v) for v in groups.values()]
    units.sort(key=lambda u: u.start)
    return units


def _assign_topics(units: List[_Unit]) -> None:
    """Units that are not AutoStory runs take the topic of the next run (CFR
    work before a run is about that run's leg, including walking from a save
    made after the previous one), else of the run before, else none ('')."""
    nxt = None  # type: Optional[_Unit]
    for u in reversed(units):
        if u.is_run:
            nxt = u
        elif nxt is not None:
            u.topic = nxt.topic
    prev = ""
    for u in units:
        if u.is_run:
            prev = u.topic
        elif u.topic is None:
            u.topic = prev


def _range(tags: List[str]) -> str:
    seen = []  # type: List[str]
    for t in tags:
        if t not in seen:
            seen.append(t)
    if not seen:
        return ""
    return seen[0] if len(seen) == 1 else seen[0] + "-" + seen[-1]


def _what(units: List[_Unit]) -> str:
    """Checkpoints run ('jubilife-center-to-barry'), else the objective text."""
    checkpoints = []  # type: List[str]
    for u in units:
        for cp in u.checkpoints:
            if cp not in checkpoints:
                checkpoints.append(cp)
    if checkpoints:
        first = checkpoints[0].replace("_", "-")
        if len(checkpoints) == 1:
            return first
        last = checkpoints[-1].replace("_", "-")
        common = 0
        a, b = checkpoints[0].split("_"), checkpoints[-1].split("_")
        while common < min(len(a), len(b)) - 1 and a[common] == b[common]:
            common += 1
        return first + "-to-" + "-".join(b[common:])
    objective = next((u.objective for u in units if u.objective), None)
    return _objective_text(objective)


def segment_name(series: str, units: List[_Unit], topic_what: str) -> str:
    start = min(u.start for u in units)
    end = max(u.end for u in units)
    topic = units[0].topic or ""
    if series == "story" and not any(u.is_run for u in units):
        #  Save loads for runs that are not in this trace.
        return "cfr-loads-" + _range([batch_tag(u.batch) for u in units if u.batch])
    if series == "story":
        tags = _range([batch_tag(u.batch) for u in units if u.batch])
        what = _what(units) or topic_what
        lead = tags or "run-" + start.strftime("%H%M")
        parts = [lead, topic if re.match(r"^\d", topic) else "", what]
    elif series == "cfr":
        tags = _range([batch_tag(u.batch) for u in units if u.batch])
        parts = ["cfr", topic if re.match(r"^\d", topic) else "", topic_what, tags]
    else:
        parts = ["keepawake", start.strftime("%H%M"), end.strftime("%H%M")]
    return "-".join(p for p in parts if p)


def segment(records: List[Dict[str, Any]], gap: _dt.timedelta = GAP
            ) -> "OrderedDict[str, List[Dict[str, Any]]]":
    """Groups records into segments: an ordered map from 'YYYY-MM-DD/name'
    (the day the segment started, then its file name without .jsonl) to its
    records in their original order. Every record lands in exactly one."""
    units = _units(records)
    _assign_topics(units)

    #  What each topic's runs did, for naming CFR segments.
    topic_runs = OrderedDict()  # type: Dict[str, List[_Unit]]
    for u in units:
        if u.is_run:
            topic_runs.setdefault(u.topic, []).append(u)
    topic_what = {t: (_what(us[:1]) or _objective_text(us[0].objective)) for t, us in topic_runs.items()}

    segments = []  # type: List[Tuple[str, List[_Unit]]]
    open_seg = {}  # type: Dict[Tuple[str, str], Tuple[_dt.datetime, List[_Unit]]]
    for u in units:
        key = (u.series, u.topic if u.series != "idle" else "")
        cur = open_seg.get(key)
        if cur is None or u.start - cur[0] > gap or u.start.date() != cur[1][0].start.date():
            members = [u]  # type: List[_Unit]
            segments.append((u.series, members))
            open_seg[key] = (u.end, members)
        else:
            cur[1].append(u)
            open_seg[key] = (max(cur[0], u.end), cur[1])

    order = {id(r): i for i, r in enumerate(records)}
    out = OrderedDict()  # type: OrderedDict[str, List[Dict[str, Any]]]
    for series, members in segments:
        name = segment_name(series, members, topic_what.get(members[0].topic or "", ""))
        day = min(u.start for u in members).strftime("%Y-%m-%d")
        key = day + "/" + name
        n = 2
        while key in out:
            key = "%s/%s-%d" % (day, name, n)
            n += 1
        recs = [r for u in members for r in u.records]
        recs.sort(key=lambda r: order[id(r)])
        out[key] = recs
    return out
