"""Physics parameter files: `games/<game>/physics.txt`.

One parameter per line: a name, a number, how it is known, and where from.
A line starting with `#` is a comment (a source may hold `#`, as in
"(#1)"); blank lines are skipped.

    # name               value  status    source
    foot.stick.per_tile  0.15   measured  games/bdsp/MEASUREMENTS.md results 2026-10-31 (#1)
    bike.tile_cost       0.5    guessed   to measure: hold times against wall-to-wall walks

The status is `measured` (on the console, with the record named in the
source), `pret` (read from a decompilation), `guessed` (the source says
how it will be measured) or `defined` (a unit, such as walking's time per
tile).

    params = load("games/bdsp/physics.txt")
    params["foot.stick.per_tile"].value      # 0.15
"""

from typing import Dict, NamedTuple

STATUSES = ("measured", "pret", "guessed", "defined")


class Param(NamedTuple):
    """One parameter: its value, how it is known, and where from."""

    value: float
    status: str
    source: str


Params = Dict[str, Param]


def parse(text: str, where: str = "physics") -> Params:
    """The parameters in `text`; `where` names it in errors."""
    params: Params = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, value, status, source = _fields(line, "%s:%d" % (where, number))
        if name in params:
            raise ValueError("%s:%d: %s given twice" % (where, number, name))
        params[name] = Param(value, status, source)
    return params


def load(path: str) -> Params:
    with open(path) as f:
        return parse(f.read(), path)


def _fields(line: str, where: str):
    parts = line.split(None, 3)
    if len(parts) < 4:
        raise ValueError("%s: want name, value, status and source: %r" % (where, line))
    name, value, status, source = parts
    try:
        number = float(value)
    except ValueError:
        raise ValueError("%s: %s: not a number: %r" % (where, name, value))
    if status not in STATUSES:
        raise ValueError("%s: %s: status %r is not one of %s" % (where, name, status, ", ".join(STATUSES)))
    return name, number, status, source
