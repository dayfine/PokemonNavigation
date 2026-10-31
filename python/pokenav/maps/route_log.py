"""Reads the planned legs of a route walk from a SerialPrograms log.

walk_route() logs, per walk:
    [Route] <label>: plan from Sandgem Town (20, 7), Sandgem Town (21, 7):
    [Route] Leg 1/8: east 9 (to wall) to Sandgem Town (29, 7), Sandgem Town (29, 8)
and while walking:
    [Walk] <label>: east 9 (to wall): blocked after 2800ms, 0 wild battle(s).
"""
import re
from dataclasses import dataclass

PLACE = re.compile(r'([A-Z][\w\' .-]*?) \((-?\d+), (-?\d+)\)')
PLAN = re.compile(r'\[Route\] (.+?): plan from (.+):\s*$')
LEG = re.compile(r'\[Route\] Leg (\d+)/(\d+): (north|south|east|west) (\d+) \((to wall|open)\) to (.+?)\s*$')
WALK = re.compile(r'\[Walk\] (.+?): (north|south|east|west) (\d+) \((?:to wall|open)\)(?:: at the wall\?)?: (\w+) after')


@dataclass
class Leg:
    direction: str
    tiles: int
    to_wall: bool
    ends: list          # [(map, x, y)], every tile the leg may end on
    stop: str = ''      # how the walk ended: blocked, limit, ...


@dataclass
class RouteWalk:
    label: str
    start: list         # [(map, x, y)]
    legs: list


def places(text):
    return [(m.group(1).strip(), int(m.group(2)), int(m.group(3))) for m in PLACE.finditer(text)]


def parse(lines, label=None):
    """Every planned walk in `lines`, or only those named `label`."""
    walks = []
    for line in lines:
        plan = PLAN.search(line)
        if plan:
            walks.append(RouteWalk(plan.group(1), places(plan.group(2)), []))
            continue
        if not walks:
            continue
        leg = LEG.search(line)
        if leg:
            walks[-1].legs.append(Leg(leg.group(3), int(leg.group(4)), leg.group(5) == 'to wall', places(leg.group(6))))
            continue
        walk = WALK.search(line)
        if walk and walks[-1].legs and walk.group(1) == walks[-1].label:
            walks[-1].legs[-1].stop = walk.group(4)
    return [w for w in walks if label is None or w.label == label]
