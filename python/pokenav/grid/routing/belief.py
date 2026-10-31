"""The robust planner: plans over sets of tiles the player may be on.

A held walk is not exact: the same hold can go a tile short or long. So the
planner tracks a belief, the set of states the player may be in, and
chooses legs that keep it small:

- a **wall** leg (hold until stopped) sends every state to where it is
  stopped, so a wall collapses the set: a row of starts walking north into
  a wall all end on the row below it;
- a **ledge** leg (hold until the first ledge hop lands) sends every state
  to the landing row, so a ledge drop pins the row just as a wall does;
- an **open** leg (hold for about n tiles) spreads it: each state may end
  anywhere from n - k to n + k tiles on, with k from an `OpenLegError`.

A leg that may run into a door, off the loaded maps, into a person or onto
unknown ground is refused: the plan could not tell where the player went.
The search is Dijkstra over beliefs, refusing any belief larger than
`max_spread`. Each planned leg says what proves it ended where planned (a
wall bump, a ledge landing, or nothing for an open leg) and the set of
states it may leave the player in.

    plan = plan_belief(world, {start}, goal=Place("Route 202", Tile(30, 19)))
    for leg in plan:
        print(describe(leg))   # "east to wall (4 tiles) -> Route 202 (30, 22)"
"""

import enum
import heapq
import itertools
from typing import AbstractSet, Callable, Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Tuple, Union

from pokenav.grid.geometry import CLOCKWISE, Direction
from pokenav.grid.maps.model import Behavior
from pokenav.grid.maps.world import Place, World
from pokenav.grid.movement import FLAT, HOLDING_REASONS, Blocked, ElevationRules, Hop, Moved, WorldState, world_step
from pokenav.grid.routing.shortest import Costs

Belief = FrozenSet[WorldState]


class LegEnd(enum.Enum):
    """How a planned leg ends, which is also what proves it ended there."""

    WALL = "wall"      #   held until the player is stopped: a wall bump
    LEDGE = "ledge"    #   held until a ledge hop lands: the landing
    OPEN = "open"      #   held for a number of tiles: nothing proves it


class OpenLegError(NamedTuple):
    """How far an open leg of n tiles may end from n: `base` + n // `per`
    tiles either way, or exactly n for legs of `exact_up_to` tiles or fewer.
    The defaults allow one tile of error up to 4 tiles, two from 5 (on BDSP a
    7-tile hold once went 9). A parameter until the physics model measures
    it."""

    base: int = 1
    per: int = 5
    exact_up_to: int = 0

    def spread(self, tiles: int) -> int:
        if tiles <= self.exact_up_to:
            return 0
        return self.base + tiles // self.per


class BeliefCosts(NamedTuple):
    """Leg costs for the robust planner. Each leg costs `per_leg` plus the
    path weights for its longest walk and its most grass, and `open_stop`
    more if it ends in the open. `max_spread` is the most states a belief may
    hold after a leg; `max_open_tiles` the longest open leg tried."""

    path: Costs = Costs()
    per_leg: float = 2.0
    open_stop: float = 8.0
    error: OpenLegError = OpenLegError()
    max_spread: int = 5
    max_open_tiles: int = 12


class PlannedLeg(NamedTuple):
    """A leg of a robust plan and the states it may leave the player in."""

    direction: Direction
    end: LegEnd
    tiles: int           #   open: the tiles to hold for; else the longest walk
    after: Belief


Goal = Union[Place, Callable[[WorldState], bool]]


def describe(leg: PlannedLeg) -> str:
    places = ", ".join(str(state.place) for state in sorted_states(leg.after))
    how = {LegEnd.WALL: "to wall", LegEnd.LEDGE: "to ledge landing", LegEnd.OPEN: "open"}[leg.end]
    return "%s %s (%d tiles) -> %s" % (leg.direction.name.lower(), how, leg.tiles, places)


def sorted_states(states: Iterable[WorldState]) -> List[WorldState]:
    """States in a fixed order: by map, row, column, elevation."""
    return sorted(states, key=lambda s: (s.place.map, s.place.tile.y, s.place.tile.x, s.elevation))


class _Walk(NamedTuple):
    """Where one state ends a walk, how far it went, the grass it crossed,
    and why it stopped."""

    end: WorldState
    tiles: int
    grass: int
    outcome: str


#   Why a walk stopped.
HELD, LIMIT, HOPPED, ESCAPED = "held", "limit", "hopped", "escaped"


class BeliefPlanner:
    """Plans robust routes on one world with one set of rules and costs."""

    def __init__(self, world: World, costs: BeliefCosts = BeliefCosts(), rules: ElevationRules = FLAT,
                 objects: AbstractSet[Place] = frozenset()):
        self.world = world
        self.costs = costs
        self.rules = rules
        self.objects = objects
        self._trajectories: Dict[Tuple[WorldState, Direction], Tuple[List[_Walk], str]] = {}
        self._open_tables: Dict[Tuple[WorldState, Direction], List[Optional[_Walk]]] = {}
        #   Brings a belief larger than max_spread back to one state, as legs
        #   with their costs; None by default. See routing.localize.
        self.localizer: Optional[Callable[[Belief], Optional[List[Tuple[PlannedLeg, float]]]]] = None

    #   ---- legs from one belief ----

    def legs_from(self, belief: Belief) -> Iterable[Tuple[PlannedLeg, float]]:
        """Every leg the planner may take from `belief`, with its cost."""
        for direction in CLOCKWISE:
            for leg in (self.wall_leg(belief, direction), self.ledge_leg(belief, direction)):
                if leg is not None:
                    yield leg
            yield from self.open_legs(belief, direction)

    def wall_leg(self, belief: Belief, direction: Direction) -> Optional[Tuple[PlannedLeg, float]]:
        walks = [self.walk(state, direction) for state in belief]
        if any(w.outcome != HELD for w in walks) or max(w.tiles for w in walks) == 0:
            return None
        return self._leg(direction, LegEnd.WALL, walks)

    def ledge_leg(self, belief: Belief, direction: Direction) -> Optional[Tuple[PlannedLeg, float]]:
        walks = [self.walk(state, direction, stop_on_hop=True) for state in belief]
        if any(w.outcome != HOPPED for w in walks):
            return None
        return self._leg(direction, LegEnd.LEDGE, walks)

    def open_legs(self, belief: Belief, direction: Direction) -> Iterable[Tuple[PlannedLeg, float]]:
        tables = [self._open_ends(state, direction) for state in belief]
        for tiles in range(1, self.costs.max_open_tiles + 1):
            spread = self.costs.error.spread(tiles)
            ends = [table[n] for table in tables for n in range(max(1, tiles - spread), tiles + spread + 1)]
            if any(end is None for end in ends):
                return
            yield self._leg(direction, LegEnd.OPEN, ends, tiles)

    def open_leg(self, belief: Belief, direction: Direction, tiles: int,
                 extra_spread: int = 0) -> Optional[Tuple[PlannedLeg, float]]:
        """One open leg of `tiles` tiles, with `extra_spread` more tiles of
        error than the error model gives, or None if it is refused."""
        spread = self.costs.error.spread(tiles) + extra_spread
        walks = [self.walk(state, direction, limit=n)
                 for state in belief for n in range(max(1, tiles - spread), tiles + spread + 1)]
        if any(w.outcome in (ESCAPED, HOPPED) for w in walks):
            return None
        return self._leg(direction, LegEnd.OPEN, walks, tiles)

    def _open_ends(self, state: WorldState, direction: Direction) -> List[Optional[_Walk]]:
        """Where a hold of n tiles from `state` ends, for every n an open leg
        may need; None where it would hop a ledge or escape. Cached."""
        key = (state, direction)
        if key not in self._open_tables:
            longest = self.costs.max_open_tiles + self.costs.error.spread(self.costs.max_open_tiles)
            ends = [self.walk(state, direction, limit=n) for n in range(longest + 1)]
            self._open_tables[key] = [None if w.outcome in (ESCAPED, HOPPED) else w for w in ends]
        return self._open_tables[key]

    def _leg(self, direction: Direction, end: LegEnd, walks: List[_Walk],
             tiles: Optional[int] = None) -> Tuple[PlannedLeg, float]:
        longest = max(w.tiles for w in walks)
        path = self.costs.path
        cost = self.costs.per_leg + path.tile * longest + path.grass * max(w.grass for w in walks)
        if end is LegEnd.OPEN:
            cost += self.costs.open_stop
        after = frozenset(w.end for w in walks)
        return PlannedLeg(direction, end, longest if tiles is None else tiles, after), cost

    def walk(self, state: WorldState, direction: Direction, limit: Optional[int] = None,
             stop_on_hop: bool = False) -> _Walk:
        """Holds `direction` from `state` until stopped, until `limit` tiles,
        or (with `stop_on_hop`) until a ledge hop lands. A hop met by an open
        leg ends it as HOPPED: the hop takes a fixed time, so the leg's
        length would not be the hold's."""
        stops, outcome = self._trajectory(state, direction)
        for walked in stops[1:]:
            hopped = walked.outcome == HOPPED
            if hopped and (stop_on_hop or limit is not None):
                return walked
            if limit is not None and walked.tiles >= limit:
                return walked._replace(outcome=LIMIT)
        last = stops[-1]
        return last._replace(outcome=outcome)

    def _trajectory(self, state: WorldState, direction: Direction) -> Tuple[List[_Walk], str]:
        """Every state a held walk passes from `state`, with the tiles and
        grass so far (a step that hopped is marked HOPPED), and how the walk
        ends: HELD or ESCAPED. Cached: beliefs share their states."""
        key = (state, direction)
        if key not in self._trajectories:
            self._trajectories[key] = self._trace(state, direction)
        return self._trajectories[key]

    def _trace(self, state: WorldState, direction: Direction) -> Tuple[List[_Walk], str]:
        stops = [_Walk(state, 0, 0, LIMIT)]
        seen = {state}
        while True:
            result = world_step(self.world, state, direction, self.rules, self.objects)
            if isinstance(result, Blocked) and result.reason in HOLDING_REASONS:
                return stops, HELD
            if not isinstance(result, (Moved, Hop)) or result.state in seen:
                return stops, ESCAPED
            state = result.state
            seen.add(state)
            last = stops[-1]
            grass = last.grass + (self.world.at(state.place).behavior is Behavior.TALL_GRASS)
            tiles = last.tiles + (2 if isinstance(result, Hop) else 1)
            stops.append(_Walk(state, tiles, grass, HOPPED if isinstance(result, Hop) else LIMIT))

    #   ---- search ----

    def plan(self, start: Iterable[WorldState], goal: Goal) -> Optional[List[PlannedLeg]]:
        """The cheapest legs that take every state in `start` to states that
        all meet `goal`, or None.

        A* over beliefs. The estimate for a belief is the most tiles any of
        its states still has to walk to the goal, times the tile cost: every
        leg costs at least that weight per tile each state walks, so the
        estimate never overshoots."""
        is_goal = goal if callable(goal) else (lambda state: state.place == goal)
        first: Belief = frozenset(start)
        to_goal = self._tiles_to_goal(first, is_goal)
        estimate = lambda belief: self.costs.path.tile * max(to_goal.get(s, float("inf")) for s in belief)
        order = itertools.count()
        best: Dict[Belief, float] = {first: 0.0}
        came_from: Dict[Belief, Tuple[Belief, List[PlannedLeg]]] = {}
        queue = [(estimate(first), next(order), first)]
        closed = set()
        while queue:
            _, _, belief = heapq.heappop(queue)
            if belief in closed:
                continue
            closed.add(belief)
            cost = best[belief]
            if all(is_goal(state) for state in belief):
                return _legs_to(belief, came_from)
            for legs, legs_cost in self._steps_from(belief):
                after = legs[-1].after
                if after == belief:
                    continue
                if cost + legs_cost < best.get(after, float("inf")):
                    best[after] = cost + legs_cost
                    came_from[after] = (belief, legs)
                    heapq.heappush(queue, (cost + legs_cost + estimate(after), next(order), after))
        return None

    def _steps_from(self, belief: Belief) -> Iterable[Tuple[List[PlannedLeg], float]]:
        """Each leg from `belief` that keeps it within `max_spread`; a leg
        that spreads it further is kept only if the `localizer` (see
        `routing.localize`) brings it back to one state, and then comes with
        the localizing legs after it."""
        for leg, leg_cost in self.legs_from(belief):
            if len(leg.after) <= self.costs.max_spread:
                yield [leg], leg_cost
                continue
            tail = self.localizer(leg.after) if self.localizer is not None else None
            if tail is not None:
                yield [leg] + [t for t, _ in tail], leg_cost + sum(c for _, c in tail)

    def _tiles_to_goal(self, start: Belief, is_goal: Callable[[WorldState], bool]) -> Dict[WorldState, int]:
        """For every state reachable from `start` one press at a time, the
        fewest tiles to a goal state (a hop counts 2). States that cannot
        reach the goal are left out."""
        reverse: Dict[WorldState, List[Tuple[WorldState, int]]] = {}
        seen = set(start)
        frontier = list(start)
        while frontier:
            state = frontier.pop()
            for direction in CLOCKWISE:
                result = world_step(self.world, state, direction, self.rules, self.objects)
                if not isinstance(result, (Moved, Hop)):
                    continue
                tiles = 2 if isinstance(result, Hop) else 1
                reverse.setdefault(result.state, []).append((state, tiles))
                if result.state not in seen:
                    seen.add(result.state)
                    frontier.append(result.state)
        return _distances_from([state for state in seen if is_goal(state)], reverse)


def _distances_from(sources: List[WorldState], edges: Dict[WorldState, List[Tuple[WorldState, int]]]) -> Dict[WorldState, int]:
    """Dijkstra from `sources` over weighted `edges`."""
    distance = {state: 0 for state in sources}
    queue = [(0, i, state) for i, state in enumerate(sources)]
    order = itertools.count(len(sources))
    while queue:
        d, _, state = heapq.heappop(queue)
        if d > distance[state]:
            continue
        for previous, tiles in edges.get(state, []):
            if d + tiles < distance.get(previous, float("inf")):
                distance[previous] = d + tiles
                heapq.heappush(queue, (d + tiles, next(order), previous))
    return distance


def plan_belief(world: World, start: Iterable[WorldState], goal: Goal, costs: BeliefCosts = BeliefCosts(),
                rules: ElevationRules = FLAT, objects: AbstractSet[Place] = frozenset()) -> Optional[List[PlannedLeg]]:
    """`BeliefPlanner(world, costs, rules, objects).plan(start, goal)`."""
    return BeliefPlanner(world, costs, rules, objects).plan(start, goal)


def _legs_to(belief: Belief, came_from: Dict[Belief, Tuple[Belief, List[PlannedLeg]]]) -> List[PlannedLeg]:
    steps = []
    while belief in came_from:
        belief, legs = came_from[belief]
        steps.append(legs)
    steps.reverse()
    return [leg for legs in steps for leg in legs]
