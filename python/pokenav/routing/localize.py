"""Localizing legs: short sequences of wall and ledge legs that send every
state of a region to one state, wherever in the region the player starts.

These are synchronizing words of the walk: "north to the wall, then west to
the wall" puts a player anywhere in an open room in its north-west corner.
The tile they end on is an anchor: the walk proves the player is there. A
region has no such sequence when no wall or ledge brings its states together,
for example two rooms that look the same from inside.

`synchronize` finds the shortest sequence (fewest legs, then cheapest) by
breadth-first search over beliefs, using only legs whose end proves where
they stopped. `use_localization` lets the robust planner insert one after a
leg that spreads the belief past `max_spread`.

    planner = BeliefPlanner(world)
    legs = synchronize(planner, room_tiles)        # e.g. [north to wall, west to wall]
    anchor(legs)                                   # the state it ends on
    use_localization(planner, max_legs=3)          # plan() may now localize
"""

from typing import Dict, Iterable, List, Optional, Tuple

from pokenav.geometry import CLOCKWISE
from pokenav.movement import WorldState
from pokenav.routing.belief import Belief, BeliefPlanner, PlannedLeg

#   The most legs a localizing sequence may have by default: a corner takes
#   two, a corner behind an obstacle three.
MAX_LEGS = 3

LocalizingLegs = List[Tuple[PlannedLeg, float]]


def synchronize(planner: BeliefPlanner, region: Iterable[WorldState], max_legs: int = MAX_LEGS) -> Optional[LocalizingLegs]:
    """The fewest wall and ledge legs (cheapest among those) that take every
    state of `region` to one state, with each leg's cost, or None if there is
    none within `max_legs`. An empty list if `region` is one state."""
    start: Belief = frozenset(region)
    if len(start) == 1:
        return []
    layer: Dict[Belief, Tuple[float, LocalizingLegs]] = {start: (0.0, [])}
    seen = {start}
    for _ in range(max_legs):
        layer = _next_layer(planner, layer, seen)
        singles = [(cost, legs) for belief, (cost, legs) in layer.items() if len(belief) == 1]
        if singles:
            return min(singles, key=lambda found: found[0])[1]
        if not layer:
            return None
    return None


def anchor(legs: LocalizingLegs) -> Optional[WorldState]:
    """The state a localizing sequence ends on, or None if it is empty."""
    if not legs:
        return None
    (state,) = legs[-1][0].after
    return state


def use_localization(planner: BeliefPlanner, max_legs: int = MAX_LEGS) -> BeliefPlanner:
    """Lets `planner` take a leg that spreads the belief past `max_spread`
    when a localizing sequence of at most `max_legs` legs follows it.
    Returns the planner."""
    cache: Dict[Belief, Optional[LocalizingLegs]] = {}

    def localizer(belief: Belief) -> Optional[LocalizingLegs]:
        if belief not in cache:
            cache[belief] = synchronize(planner, belief, max_legs)
        return cache[belief]

    planner.localizer = localizer
    return planner


def _next_layer(planner: BeliefPlanner, layer: Dict[Belief, Tuple[float, LocalizingLegs]],
                seen: set) -> Dict[Belief, Tuple[float, LocalizingLegs]]:
    """Every belief one proving leg on from `layer`, with the cheapest way
    there; beliefs met before are left out."""
    following: Dict[Belief, Tuple[float, LocalizingLegs]] = {}
    for belief, (cost, legs) in layer.items():
        for leg, leg_cost in _proving_legs(planner, belief):
            if leg.after in seen:
                continue
            total = cost + leg_cost
            if leg.after not in following or total < following[leg.after][0]:
                following[leg.after] = (total, legs + [(leg, leg_cost)])
    seen.update(following)
    return following


def _proving_legs(planner: BeliefPlanner, belief: Belief) -> Iterable[Tuple[PlannedLeg, float]]:
    for direction in CLOCKWISE:
        for found in (planner.wall_leg(belief, direction), planner.ledge_leg(belief, direction)):
            if found is not None:
                yield found
