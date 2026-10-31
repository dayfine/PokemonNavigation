"""The robust planner: plans over sets of tiles the player may be on.

A held walk is not exact: the same hold can go a tile short or long. So the
planner tracks a belief, the set of states the player may be in, and
chooses legs that keep it small:

- a **wall** leg (hold until stopped) sends every state to where it is
  stopped, so a wall collapses the set: a row of starts walking north into
  a wall all end on the row below it;
- a **ledge** leg (hold until the first ledge hop lands) sends every state
  to the landing row, so a ledge drop pins the row just as a wall does;
- an **open** leg (about n tiles) spreads it: each state may end anywhere
  from n - k to n + k tiles on. It is walked as counted D-pad taps or as a
  timed stick hold (`routing.execution`), each with its own k from the
  game's error model (`physics.model.TileError`): BDSP's taps are exact
  (k = 0), its stick holds are off by about 0.15 tile a tile, so holds up to
  11 tiles land exactly and a 14-tile hold may miss by one;
- a **door** leg steps through the door ahead, into a loaded map or onto the
  goal;
- an **event** leg holds until a story scene starts (walking north from
  Jubilife's gate until Rowan's scene): every state ends on the first of the
  planner's `events` tiles it reaches. The scene leaves the player wherever
  it leaves them, so an event leg ends the plan: the goal must be met on
  those tiles.

A plan starts from one known tile: the bot clips to a wall or corner before
it plans, and from there the position is known after every exact leg. The
belief only grows at an open leg, and must be absorbed by what follows: a
wall or ledge leg, or a goal region wider than the spread (a 14-tile hold
into a 4-wide street). A leg that may run into a door, off the loaded maps,
into a person or onto unknown ground is refused: the plan could not tell
where the player went.
With a game's `ExecutionModel` the search also tracks the facing (a D-pad or
door leg toward a new direction starts with a tap that only turns, which
costs `turn_tap`) and, when the player has a bike, the mode.
The search is Dijkstra over beliefs, refusing any belief larger than
`max_spread` (3 by default: the most spread measured). Each planned leg
says what proves it ended where planned (a wall bump, a ledge landing, or
nothing for an open leg) and the set of states it may leave the player in.

    plan = plan_belief(world, start, goal=Place("Route 202", Tile(30, 19)))
    for leg in plan:
        print(describe(leg))   # "clip east (4 tiles) -> Route 202 (30, 22)"
"""

import enum
import heapq
import itertools
from typing import AbstractSet, Callable, Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Tuple, Union

from pokenav.grid.geometry import CLOCKWISE, Direction
from pokenav.grid.maps.model import Behavior
from pokenav.grid.maps.world import Place, World
from pokenav.grid.movement import (
    FLAT, HOLDING_REASONS, Blocked, ElevationRules, Hop, Moved, Warp, Warped, WorldState, world_step,
)
from pokenav.grid.routing.execution import TAPPED, Execution
from pokenav.grid.routing.shortest import Costs
from pokenav.physics.model import ExecutionModel, Mode, ModeModel, TileError

Belief = FrozenSet[WorldState]


class LegEnd(enum.Enum):
    """How a planned leg ends, which is also what proves it ended there."""

    WALL = "wall"      #   held until the player is stopped: a wall bump
    LEDGE = "ledge"    #   held until a ledge hop lands: the landing
    OPEN = "open"      #   a number of tiles: nothing proves it, unless each tap is checked
    DOOR = "door"      #   through the door ahead: the fade
    EVENT = "event"    #   held until a story scene starts: the scene


#   A stick hold's error as measured on BDSP (games/bdsp/MEASUREMENTS.md
#   results 2026-10-31, #1 and #3): about 0.15 tile a tile, with no slide
#   after letting go. The default until a game's parameter file gives its own.
MEASURED_STICK = TileError(per_tile=0.15)

#   The most states a belief may hold by default. On the 2026-10-31 BDSP runs
#   no open leg spread further than a tile either way; a wider belief wants a
#   wall leg first.
MAX_SPREAD = 3


class BeliefCosts(NamedTuple):
    """Leg costs for the robust planner. Each leg costs `per_leg` plus the
    path weights for its longest walk and its most grass, and `open_stop`
    more if it ends in the open on a timed hold or a tap that may miss.
    `max_spread` is the most states a belief may hold after a leg;
    `max_open_tiles` the longest open leg tried. `execution` is the game's
    model of walking (see `physics.model`); without one the planner walks on
    foot with stick holds whose error is `error` (which, by default, says
    nothing about sideways drift)."""

    path: Costs = Costs()
    per_leg: float = 2.0
    open_stop: float = 8.0
    error: TileError = MEASURED_STICK
    max_spread: int = MAX_SPREAD
    max_open_tiles: int = 12
    execution: Optional[ExecutionModel] = None


class PlannedLeg(NamedTuple):
    """A leg of a robust plan, how it is walked, and the states it may leave
    the player in."""

    direction: Direction
    end: LegEnd
    tiles: int           #   open: the tiles to count; else the longest walk
    after: Belief
    execution: Execution
    mode: Mode = Mode.FOOT


#   A search node: the belief, the facing (None: not known) and the mode.
class _Node(NamedTuple):
    belief: Belief
    facing: Optional[Direction]
    mode: Mode


Goal = Union[Place, Callable[[WorldState], bool]]


def describe(leg: PlannedLeg) -> str:
    """A leg in words, e.g. "dpad west (20 tiles) -> Oreburgh City (2, 2)"."""
    places = ", ".join(str(state.place) for state in sorted_states(leg.after))
    bike = "bike " if leg.mode is Mode.BIKE else ""
    return "%s%s %s (%d tiles) -> %s" % (bike, leg.execution.value, leg.direction.name.lower(), leg.tiles, places)


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
HELD, LIMIT, HOPPED, ESCAPED, EVENT = "held", "limit", "hopped", "escaped", "event"

#   What lies beside a tile of a held walk: a wall the drift presses against
#   (a building's front with its door counts: the door opens only to a step
#   into it), open ground of the same corridor, or something the drift must
#   not meet (a ledge, a warp tile, a person, the unknown, a map edge).
WALL_SIDE, OPEN_SIDE, HAZARD_SIDE = "wall", "open", "hazard"

#   How each leg end is walked when it is not counted.
_UNCOUNTED = {LegEnd.WALL: Execution.CLIP, LegEnd.LEDGE: Execution.LEDGE}


class BeliefPlanner:
    """Plans robust routes on one world with one set of rules and costs."""

    def __init__(self, world: World, costs: BeliefCosts = BeliefCosts(), rules: ElevationRules = FLAT,
                 objects: AbstractSet[Place] = frozenset(), events: AbstractSet[Place] = frozenset()):
        """`objects` are tiles a person or thing stands on; `events` are
        tiles that start a story scene when stepped on."""
        self.world = world
        self.costs = costs
        self.rules = rules
        self.objects = objects
        self.events = events
        self._trajectories: Dict[Tuple[WorldState, Direction], Tuple[List[_Walk], str]] = {}
        self._open_tables: Dict[Tuple[WorldState, Direction], List[Optional[_Walk]]] = {}
        self._flanks: Dict[Tuple[WorldState, Direction], List[Tuple[str, str]]] = {}
        self.model = costs.execution or ExecutionModel(foot=ModeModel(tile_cost=1.0, dpad=None, stick=costs.error))
        self._longest = costs.max_open_tiles + max(error.spread(costs.max_open_tiles) for error in self._errors())
        #   Brings a belief larger than max_spread back to one state, as legs
        #   with their costs; None by default. See routing.localize.
        self.localizer: Optional[Callable[[Belief], Optional[List[Tuple[PlannedLeg, float]]]]] = None

    #   ---- legs from one belief ----

    def legs_from(self, belief: Belief, modes: Iterable[Mode] = (Mode.FOOT,)) -> Iterable[Tuple[PlannedLeg, float]]:
        """Every leg the planner may take from `belief` in `modes`, with its
        cost (not counting turn taps or getting on or off the bike)."""
        for mode in modes:
            counted = [kind for kind in (Execution.DPAD, Execution.STICK_HOLD) if self.error(kind, mode) is not None]
            to_wall = [Execution.CLIP] + ([Execution.RUN] if self.model.mode(mode).run is not None else [])
            for direction in CLOCKWISE:
                legs = [self.wall_leg(belief, direction, mode, kind) for kind in to_wall]
                legs += [self.ledge_leg(belief, direction, mode), self.door_leg(belief, direction, mode),
                         self.event_leg(belief, direction, mode)]
                for leg in legs:
                    if leg is not None:
                        yield leg
                for kind in counted:
                    yield from self.open_legs(belief, direction, kind, mode)

    def wall_leg(self, belief: Belief, direction: Direction, mode: Mode = Mode.FOOT,
                 kind: Execution = Execution.CLIP) -> Optional[Tuple[PlannedLeg, float]]:
        """A hold until stopped against a wall, walked (CLIP) or run (RUN,
        if the mode has running); None unless every state is held."""
        walks = [self.walk(state, direction) for state in belief]
        if any(w.outcome != HELD for w in walks) or max(w.tiles for w in walks) == 0:
            return None
        if not self._held_safely(belief, direction, walks, mode):
            return None
        if kind is Execution.RUN and self.model.mode(mode).run is None:
            return None
        return self._leg(direction, LegEnd.WALL, walks, mode, kind)

    def ledge_leg(self, belief: Belief, direction: Direction, mode: Mode = Mode.FOOT) -> Optional[Tuple[PlannedLeg, float]]:
        walks = [self.walk(state, direction, stop_on_hop=True) for state in belief]
        if any(w.outcome != HOPPED for w in walks):
            return None
        if not self._held_safely(belief, direction, walks, mode):
            return None
        return self._leg(direction, LegEnd.LEDGE, walks, mode)

    def event_leg(self, belief: Belief, direction: Direction, mode: Mode = Mode.FOOT) -> Optional[Tuple[PlannedLeg, float]]:
        """A hold until a story scene starts: each state ends on the first
        event tile it reaches. None unless every state's walk reaches one."""
        walks = [self.walk(state, direction) for state in belief]
        if any(w.outcome != EVENT for w in walks):
            return None
        if not self._held_safely(belief, direction, walks, mode):
            return None
        return self._leg(direction, LegEnd.EVENT, walks, mode, Execution.EVENT)

    def door_leg(self, belief: Belief, direction: Direction, mode: Mode = Mode.FOOT) -> Optional[Tuple[PlannedLeg, float]]:
        """A step through the door ahead of every state: each lands where the
        warp leads, or, for a warp into a map not loaded, on the door tile.
        None unless every state is in front of a door or warp."""
        ends = []
        for state in belief:
            result = world_step(self.world, state, direction, self.rules, self.objects)
            if not isinstance(result, (Warp, Warped)):
                return None
            ends.append(_pressed_to(state, result))
        cost = self.costs.per_leg + self.costs.path.tile * self.model.mode(mode).tile_cost + self.model.door
        return PlannedLeg(direction, LegEnd.DOOR, 1, frozenset(ends), Execution.DOOR, mode), cost

    def error(self, kind: Execution, mode: Mode = Mode.FOOT):
        """The error model of a counted leg `kind` in `mode`, or None if the
        game does not count legs that way (or has no such mode)."""
        model = self.model.mode(mode)
        if model is None:
            return None
        return model.dpad if kind is Execution.DPAD else model.stick

    def open_legs(self, belief: Belief, direction: Direction, kind: Execution = Execution.STICK_HOLD,
                  mode: Mode = Mode.FOOT) -> Iterable[Tuple[PlannedLeg, float]]:
        error = self.error(kind, mode)
        tables = [self._open_ends(state, direction) for state in belief]
        for tiles in range(1, self.costs.max_open_tiles + 1):
            spread = error.spread(tiles)
            ends = [table[n] for table in tables for n in range(max(1, tiles - spread), tiles + spread + 1)]
            if any(end is None for end in ends):
                return
            if error.lateral > 0 and not self.drifts_safely(belief, direction, tiles + spread):
                return
            yield self._leg(direction, LegEnd.OPEN, ends, mode, kind, tiles, spread)

    def open_leg(self, belief: Belief, direction: Direction, tiles: int, extra_spread: int = 0,
                 kind: Execution = Execution.STICK_HOLD, mode: Mode = Mode.FOOT) -> Optional[Tuple[PlannedLeg, float]]:
        """One open leg of `tiles` tiles walked as `kind`, with `extra_spread`
        more tiles of error than the error model gives, or None if it is
        refused."""
        error = self.error(kind, mode)
        spread = error.spread(tiles) + extra_spread
        walks = [self.walk(state, direction, limit=n)
                 for state in belief for n in range(max(1, tiles - spread), tiles + spread + 1)]
        if any(w.outcome in (ESCAPED, HOPPED, EVENT) for w in walks):
            return None
        if error.lateral > 0 and not self.drifts_safely(belief, direction, tiles + spread):
            return None
        return self._leg(direction, LegEnd.OPEN, walks, mode, kind, tiles, spread)

    #   ---- sideways drift ----

    def _held_safely(self, belief: Belief, direction: Direction, walks: List[_Walk], mode: Mode) -> bool:
        """Whether a leg held with the stick (a clip, a run, a ledge or an
        event leg) from `belief` is safe from drifting sideways, by the
        mode's stick error."""
        if self.model.mode(mode).stick.lateral <= 0:
            return True
        return self.drifts_safely(belief, direction, max(w.tiles for w in walks))

    def drifts_safely(self, belief: Belief, direction: Direction, tiles: int) -> bool:
        """Whether a stick hold of up to `tiles` tiles from every state of
        `belief` keeps its row: on each side, what lies beside the tiles it
        passes is all wall (the drift presses against it) or all open ground
        (the same corridor). A side that changes from wall to open has
        corners the drift catches on, and a ledge, warp tile, person, map
        edge or unknown tile beside the walk must not be drifted into."""
        for state in belief:
            flanks = self.flanks(state, direction)[:tiles + 1]
            for side in (0, 1):
                kinds = {flank[side] for flank in flanks}
                if kinds not in ({WALL_SIDE}, {OPEN_SIDE}):
                    return False
        return True

    def flanks(self, state: WorldState, direction: Direction) -> List[Tuple[str, str]]:
        """What lies to the left and right of each tile of the held walk from
        `state` (the start tile first): WALL_SIDE, OPEN_SIDE or HAZARD_SIDE.
        Cached."""
        key = (state, direction)
        if key not in self._flanks:
            stops, _ = self._trajectory(state, direction)
            sides = (direction.turn(clockwise=False), direction.turn(clockwise=True))
            self._flanks[key] = [tuple(self._side(stop.end, side) for side in sides) for stop in stops]
        return self._flanks[key]

    def _side(self, state: WorldState, side: Direction) -> str:
        result = world_step(self.world, state, side, self.rules, self.objects)
        if isinstance(result, Blocked) and result.reason in HOLDING_REASONS:
            return WALL_SIDE
        if isinstance(result, Moved):
            return OPEN_SIDE
        if isinstance(result, (Warp, Warped)):
            beside = Place(state.place.map, state.place.tile.step(side))
            if self.world.at(beside).behavior is Behavior.DOOR:
                return WALL_SIDE
        return HAZARD_SIDE

    def _errors(self):
        """Every counted-leg error model the game has."""
        return [error for model in (self.model.foot, self.model.bike) if model is not None
                for error in (model.dpad, model.stick) if error is not None]

    def _open_ends(self, state: WorldState, direction: Direction) -> List[Optional[_Walk]]:
        """Where a hold of n tiles from `state` ends, for every n an open leg
        may need; None where it would hop a ledge or escape. Cached."""
        key = (state, direction)
        if key not in self._open_tables:
            ends = [self.walk(state, direction, limit=n) for n in range(self._longest + 1)]
            self._open_tables[key] = [None if w.outcome in (ESCAPED, HOPPED, EVENT) else w for w in ends]
        return self._open_tables[key]

    def _leg(self, direction: Direction, end: LegEnd, walks: List[_Walk], mode: Mode,
             kind: Optional[Execution] = None, tiles: Optional[int] = None,
             spread: int = 0) -> Tuple[PlannedLeg, float]:
        """A leg and its cost. A counted leg pays `open_stop` when it is a
        timed hold (an interruption leaves the player at a guess) or may end
        off its tile; checked taps that land exactly do not. A run (B held)
        pays the mode's running time a tile."""
        longest = max(w.tiles for w in walks)
        path = self.costs.path
        model = self.model.mode(mode)
        tile_cost = path.tile * (model.run if kind is Execution.RUN else model.tile_cost)
        cost = self.costs.per_leg + tile_cost * longest + path.grass * max(w.grass for w in walks)
        if kind is Execution.STICK_HOLD or spread > 0:
            cost += self.costs.open_stop
        after = frozenset(w.end for w in walks)
        execution = kind if kind is not None else _UNCOUNTED[end]
        return PlannedLeg(direction, end, longest if tiles is None else tiles, after, execution, mode), cost

    def walk(self, state: WorldState, direction: Direction, limit: Optional[int] = None,
             stop_on_hop: bool = False) -> _Walk:
        """Holds `direction` from `state` until stopped, until `limit` tiles,
        or (with `stop_on_hop`) until a ledge hop lands. A hop met by an open
        leg ends it as HOPPED: the hop takes a fixed time, so the leg's
        length would not be the hold's. A story scene ends any walk as
        EVENT."""
        stops, outcome = self._trajectory(state, direction)
        for walked in stops[1:]:
            if walked.outcome == EVENT:
                return walked
            hopped = walked.outcome == HOPPED
            if hopped and (stop_on_hop or limit is not None):
                return walked
            if limit is not None and walked.tiles >= limit:
                return walked._replace(outcome=LIMIT)
        last = stops[-1]
        return last._replace(outcome=outcome)

    def _trajectory(self, state: WorldState, direction: Direction) -> Tuple[List[_Walk], str]:
        """Every state a held walk passes from `state`, with the tiles and
        grass so far (a step that hopped is marked HOPPED, the step onto an
        event tile EVENT), and how the walk ends: HELD, ESCAPED or EVENT.
        Cached: beliefs share their states."""
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
            if state.place in self.events:
                stops.append(_Walk(state, tiles, grass, EVENT))
                return stops, EVENT
            stops.append(_Walk(state, tiles, grass, HOPPED if isinstance(result, Hop) else LIMIT))

    #   ---- search ----

    def plan(self, start: WorldState, goal: Goal, facing: Optional[Direction] = None,
             bike: bool = False) -> Optional[List[PlannedLeg]]:
        """The cheapest legs from `start`, one known state, to states that
        all meet `goal`, or None. Raises TypeError for a set of states: clip
        to a wall first (`routing.localize` finds the legs), then plan.
        `facing` is the start facing (None: not known); with `bike`, legs may
        be ridden (if the game has a bike).

        A* over (belief, facing, mode). The estimate for a belief is the most
        tiles any of its states still has to walk to the goal, times the
        cheapest tile cost: every leg costs at least that per tile each state
        walks, so the estimate never overshoots."""
        if not isinstance(start, WorldState):
            raise TypeError("plan from one known state, not %r" % (start,))
        is_goal = goal if callable(goal) else (lambda state: state.place == goal)
        modes = [Mode.FOOT] + ([Mode.BIKE] if bike and self.model.bike is not None else [])
        tile = self.costs.path.tile * min(_fastest(self.model.mode(mode)) for mode in modes)
        first = _Node(frozenset({start}), facing, Mode.FOOT)
        to_goal = self._tiles_to_goal(first.belief, is_goal)
        estimate = lambda node: tile * max(to_goal.get(s, float("inf")) for s in node.belief)
        order = itertools.count()
        best: Dict[_Node, float] = {first: 0.0}
        came_from: Dict[_Node, Tuple[_Node, List[PlannedLeg]]] = {}
        queue = [(estimate(first), next(order), first)]
        closed = set()
        while queue:
            _, _, node = heapq.heappop(queue)
            if node in closed:
                continue
            closed.add(node)
            cost = best[node]
            if all(is_goal(state) for state in node.belief):
                return _legs_to(node, came_from)
            for legs, legs_cost in self._steps_from(node, modes, is_goal):
                last = legs[-1]
                if last.after == node.belief:
                    continue
                after = _Node(last.after, None if last.end is LegEnd.DOOR else last.direction, last.mode)
                if cost + legs_cost < best.get(after, float("inf")):
                    best[after] = cost + legs_cost
                    came_from[after] = (node, legs)
                    heapq.heappush(queue, (cost + legs_cost + estimate(after), next(order), after))
        return None

    def _steps_from(self, node: _Node, modes: List[Mode],
                    is_goal: Callable[[WorldState], bool]) -> Iterable[Tuple[List[PlannedLeg], float]]:
        """Each leg from `node` that keeps the belief within `max_spread`; a
        leg that spreads it further is kept only if the `localizer` (see
        `routing.localize`) brings it back to one state, and then comes with
        the localizing legs after it. A door leg is kept if it reaches the
        goal or another loaded map; an event leg only if it reaches the
        goal, as the scene ends the plan."""
        for leg, leg_cost in self.legs_from(node.belief, modes):
            if leg.end is LegEnd.DOOR and not _door_leads_on(node.belief, leg, is_goal):
                continue
            if leg.end is LegEnd.EVENT and not all(is_goal(state) for state in leg.after):
                continue
            leg_cost += self._start_cost(node, leg)
            if len(leg.after) <= self.costs.max_spread:
                yield [leg], leg_cost
                continue
            tail = self.localizer(leg.after) if self.localizer is not None else None
            if tail is not None:
                tail_legs = [t._replace(mode=leg.mode) for t, _ in tail]
                yield [leg] + tail_legs, leg_cost + sum(c for _, c in tail)

    def _start_cost(self, node: _Node, leg: PlannedLeg) -> float:
        """What starting `leg` from `node` costs before it moves: a tap that
        only turns, for a leg started with a tap toward a new direction; and
        getting on or off the bike."""
        cost = 0.0
        if leg.execution in TAPPED and leg.direction is not node.facing:
            cost += self.model.turn_tap
        if leg.mode is not node.mode:
            cost += self.model.mount
        return cost

    def _tiles_to_goal(self, start: Belief, is_goal: Callable[[WorldState], bool]) -> Dict[WorldState, int]:
        """For every state reachable from `start` one press at a time, the
        fewest tiles to a goal state (a hop counts 2, a door 1). States that
        cannot reach the goal are left out."""
        reverse: Dict[WorldState, List[Tuple[WorldState, int]]] = {}
        seen = set(start)
        frontier = list(start)
        while frontier:
            state = frontier.pop()
            for direction in CLOCKWISE:
                result = world_step(self.world, state, direction, self.rules, self.objects)
                after = _pressed_to(state, result)
                if after is None:
                    continue
                tiles = 2 if isinstance(result, Hop) else 1
                reverse.setdefault(after, []).append((state, tiles))
                if after not in seen:
                    seen.add(after)
                    frontier.append(after)
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


def plan_belief(world: World, start: WorldState, goal: Goal, costs: BeliefCosts = BeliefCosts(),
                rules: ElevationRules = FLAT, objects: AbstractSet[Place] = frozenset(),
                facing: Optional[Direction] = None, bike: bool = False,
                events: AbstractSet[Place] = frozenset()) -> Optional[List[PlannedLeg]]:
    """`BeliefPlanner(world, costs, rules, objects, events).plan(start, goal, facing, bike)`."""
    return BeliefPlanner(world, costs, rules, objects, events).plan(start, goal, facing, bike)


def _fastest(model: ModeModel) -> float:
    """The least a tile costs in `model`: running's, if it has running."""
    return model.tile_cost if model.run is None else min(model.tile_cost, model.run)


def _pressed_to(state: WorldState, result) -> Optional[WorldState]:
    """Where one press from `state` leaves the player, or None if it does not
    move them: a door into a map not loaded leaves them on the door tile."""
    if isinstance(result, (Moved, Hop, Warped)):
        return result.state
    if isinstance(result, Warp):
        return WorldState(Place(state.place.map, result.tile), state.elevation)
    return None


def _door_leads_on(before: Belief, leg: PlannedLeg, is_goal: Callable[[WorldState], bool]) -> bool:
    """Whether a door leg reaches the goal or another loaded map, rather than
    a door into a map not loaded that the route only passes."""
    return all(is_goal(state) for state in leg.after) or (
        {s.place.map for s in leg.after} != {s.place.map for s in before})


def _legs_to(node: _Node, came_from: Dict[_Node, Tuple[_Node, List[PlannedLeg]]]) -> List[PlannedLeg]:
    steps = []
    while node in came_from:
        node, legs = came_from[node]
        steps.append(legs)
    steps.reverse()
    return [leg for legs in steps for leg in legs]
