"""Shared helpers for trace records: times, directions, the record shape."""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Optional

SCHEMA_VERSION = 1

#  Timestamps are the lab app's local wall clock, without a zone.
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def parse_log_time(text: str) -> _dt.datetime:
    """'2026-10-30 20:49:14.351842' -> datetime."""
    return _dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")


def format_time(t: _dt.datetime) -> str:
    """ISO local time to the millisecond: '2026-10-30T20:49:14.351'."""
    return t.strftime(TIME_FORMAT)[:-3]


def parse_since(text: str, today: Optional[_dt.date] = None) -> _dt.datetime:
    """Accepts '2026-10-30', '2026-10-30 20:49', '2026-10-30T20:49:14.3',
    or a time of day ('20:49', '20:49:14') meaning today."""
    text = text.strip().replace("T", " ")
    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return _dt.datetime.strptime(text, fmt)
        except ValueError:
            pass
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
        try:
            clock = _dt.datetime.strptime(text, fmt).time()
        except ValueError:
            continue
        day = today or _dt.date.today()
        return _dt.datetime.combine(day, clock)
    raise ValueError("unrecognized time: " + repr(text))


def stick_direction(x: float, y: float) -> str:
    """Compass direction of a stick position. y = +1 is north (up).
    Returns '' for a centred stick, a two-letter name for a diagonal."""
    eps = 0.25
    ns = "N" if y > eps else ("S" if y < -eps else "")
    ew = "E" if x > eps else ("W" if x < -eps else "")
    return ns + ew


DPAD_DIRECTIONS = {
    "up": "N", "down": "S", "left": "W", "right": "E",
    "UP": "N", "DOWN": "S", "LEFT": "W", "RIGHT": "E",
}

WALK_STOPS = ("arrived", "dialog", "transition", "blocked", "limit")


def new_record(kind: str, t: _dt.datetime, source: str) -> Dict[str, Any]:
    """A record with the fields every record has. Unknown values are None."""
    return {
        "v": SCHEMA_VERSION,
        "kind": kind,
        "t": format_time(t),
        "t_end": None,
        "source": source,
        "program": None,
        "run_start": None,
        "batch": None,
        "line": None,
        "command": None,
        "objective": None,
        "checkpoint": None,
        "event": None,
        "input": None,
        "role": None,
        "run": None,
        "label": None,
        "outcome": None,
        "moving_ms": None,
        "total_ms": None,
        "slice_ms": None,
        "changes": None,
        "still_threshold": None,
        "wild_battles": None,
        "notes": None,
        "screenshot": None,
        "screenshot_after_ms": None,
    }


def stick_input(x: float, y: float, hold_ms: Optional[int], release_ms: Optional[int],
                stick: str = "L") -> Dict[str, Any]:
    """A stick position; a walk's stick has no hold or release of its own."""
    inp = {"type": "stick", "stick": stick, "x": x, "y": y, "dir": stick_direction(x, y)}
    if hold_ms is not None:
        inp["hold_ms"] = hold_ms
    if release_ms is not None:
        inp["release_ms"] = release_ms
    return inp


def button_input(buttons: str, hold_ms: Optional[int], release_ms: Optional[int]) -> Dict[str, Any]:
    return {"type": "button", "buttons": buttons, "hold_ms": hold_ms, "release_ms": release_ms}


def dpad_input(direction: str, hold_ms: Optional[int], release_ms: Optional[int]) -> Dict[str, Any]:
    return {
        "type": "dpad",
        "dir": DPAD_DIRECTIONS.get(direction, direction),
        "hold_ms": hold_ms,
        "release_ms": release_ms,
    }

