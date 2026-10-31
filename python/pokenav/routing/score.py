"""Score and rank routes the way a person judges them: by risk, not length.

A route is a list of planned legs (`routing.belief.PlannedLeg`). Its score
is a vector:

- `risk`: the open legs ("unprotected moves"), each counted as
  1 / (1 + margin), where its margin is how many tiles of extra error it
  takes before the route fails. A wide margin makes an open leg cheap.
- `localizations`: legs that shrink the belief (a wall or a ledge landing
  after an open leg). One is good; each one past `free_localizations` counts.
- `turns` and `turnarounds` (a turn back the way the route came).
- `grass`: tall-grass tiles crossed, reported on their own.
- `tiles`: the length, last.

Routes are ranked lexicographically in `ScoreOptions.order` by default, or by
a weighted sum when `ScoreOptions.weights` is given. `checks` lists, per leg,
where the player should be and how that is proven, for the walker to check
on arrival.

    planner = BeliefPlanner(world)
    ranked = rank(planner, start, {"wall": wall_legs, "open": open_legs}, goal)
    ranked[0].name                          # "wall"
    ranked[0].score.risk
"""

from typing import Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from pokenav.maps.world import Place, World
from pokenav.movement import WorldState
from pokenav.routing.belief import Belief, BeliefPlanner, Goal, LegEnd, PlannedLeg
from pokenav.routing.shortest import Costs, Move, MoveKind, Path, shortest_path

#   The path weights `propose` tries: every pair of turn and grass weight,
#   from cutting through grass to going far round it.
PROPOSAL_TURNS = (1.0, 2.0, 3.0)
PROPOSAL_GRASS = (0.0, 3.0, 5.0, 10.0, 20.0)


class RouteScore(NamedTuple):
    """A route's score; lower is better in every field."""

    risk: float
    localizations: int
    turns: int
    turnarounds: int
    grass: int
    tiles: int


#   The default ranking: risk first, then extra localizations, turns, grass.
DEFAULT_ORDER = ("risk", "localizations", "turnarounds", "turns", "grass", "tiles")


#   Weights for ranking by a weighted sum instead. Grass is a tunable weight:
#   on Route 1 (Viridian City to Pallet Town) a grass weight of 2 or more
#   keeps the top route to the hand-drawn line's 5 grass tiles; below about
#   1.3 it cuts through 10 or more to save open legs and turns.
WEIGHTS = {"risk": 2.0, "localizations": 1.0, "turns": 1.0, "turnarounds": 1.0, "grass": 2.0, "tiles": 0.01}


class ScoreOptions(NamedTuple):
    """How routes are scored and ranked. `max_margin` caps the margin search.
    With `ledges_localize` False, a ledge leg counts as an open leg (the old
    planners' view, kept to test against). `free_localizations` are not
    counted. `weights`, if given, ranks by the weighted sum of the score's
    fields instead of `order`."""

    max_margin: int = 3
    ledges_localize: bool = True
    free_localizations: int = 1
    order: Sequence[str] = DEFAULT_ORDER
    weights: Optional[Mapping[str, float]] = None


class Ranked(NamedTuple):
    name: str
    score: RouteScore
    legs: Sequence[PlannedLeg]


class Check(NamedTuple):
    """What the walker checks after a leg: the states it may be in, and what
    proves it ("wall bump", "ledge landing", "map banner", or "none")."""

    leg: int
    expected: Belief
    proof: str


def replay(planner: BeliefPlanner, start: Iterable[WorldState], legs: Sequence[PlannedLeg],
           widen: Optional[Tuple[int, int]] = None) -> Optional[List[PlannedLeg]]:
    """The legs walked again from `start`, with each leg's belief worked out
    afresh; `widen` = (leg index, extra tiles) gives one open leg more error.
    None if a leg is refused on the way."""
    belief = frozenset(start)
    walked = []
    for i, leg in enumerate(legs):
        extra = widen[1] if widen is not None and widen[0] == i else 0
        result = _walk_leg(planner, belief, leg, extra)
        if result is None:
            return None
        walked.append(result)
        belief = result.after
    return walked


def _walk_leg(planner: BeliefPlanner, belief: Belief, leg: PlannedLeg, extra: int) -> Optional[PlannedLeg]:
    if leg.end is LegEnd.WALL:
        found = planner.wall_leg(belief, leg.direction)
    elif leg.end is LegEnd.LEDGE:
        found = planner.ledge_leg(belief, leg.direction)
    else:
        found = planner.open_leg(belief, leg.direction, leg.tiles, extra)
    return None if found is None else found[0]


def score(planner: BeliefPlanner, start: Iterable[WorldState], legs: Sequence[PlannedLeg], goal: Goal,
          options: ScoreOptions = ScoreOptions()) -> Optional[RouteScore]:
    """The score of `legs` from `start`, or None if they do not take every
    start state to the goal."""
    start = frozenset(start)
    walked = replay(planner, start, legs)
    if walked is None or not _reaches(walked, start, goal):
        return None
    risk = sum(1.0 / (1 + _margin(planner, start, legs, i, goal, options))
               for i, leg in enumerate(walked) if _unprotected(leg, options))
    turns, turnarounds = _turns(walked)
    return RouteScore(
        risk=risk,
        localizations=max(0, _localizations(start, walked, options) - options.free_localizations),
        turns=turns,
        turnarounds=turnarounds,
        grass=sum(_grass(planner, before, leg) for before, leg in zip(_beliefs(start, walked), walked)),
        tiles=sum(leg.tiles for leg in walked),
    )


def rank(planner: BeliefPlanner, start: Iterable[WorldState], routes: Mapping[str, Sequence[PlannedLeg]],
         goal: Goal, options: ScoreOptions = ScoreOptions()) -> List[Ranked]:
    """The routes that reach the goal, best first."""
    scored = []
    for name, legs in routes.items():
        result = score(planner, start, legs, goal, options)
        if result is not None:
            scored.append(Ranked(name, result, legs))
    return sorted(scored, key=lambda r: sort_key(r.score, options))


def sort_key(route_score: RouteScore, options: ScoreOptions):
    if options.weights is not None:
        return sum(weight * getattr(route_score, field) for field, weight in options.weights.items())
    return tuple(getattr(route_score, field) for field in options.order)


def propose(planner: BeliefPlanner, start: WorldState, goal: Goal,
            turns: Sequence[float] = PROPOSAL_TURNS, grass: Sequence[float] = PROPOSAL_GRASS) -> Dict[str, List[PlannedLeg]]:
    """Candidate routes: the shortest path under each pair of turn and grass
    weights, as planned legs, keeping each distinct one that can be walked.
    Names say the weights, e.g. "turn 2, grass 5"."""
    routes: Dict[str, List[PlannedLeg]] = {}
    seen = set()
    for turn in turns:
        for grass_weight in grass:
            path = shortest_path(planner.world, start, goal, Costs(turn=turn, grass=grass_weight),
                                 planner.rules, planner.objects)
            if path is None or tuple(path.moves) in seen:
                continue
            seen.add(tuple(path.moves))
            legs = legs_from_path(planner, path)
            if legs is not None:
                routes["turn %g, grass %g" % (turn, grass_weight)] = legs
    return routes


def plan_ranked(planner: BeliefPlanner, start: WorldState, goal: Goal,
                options: ScoreOptions = ScoreOptions()) -> List[Ranked]:
    """Proposes routes from `start` to `goal` and ranks them, best first."""
    return rank(planner, [start], propose(planner, start, goal), goal, options)


def checks(start: Iterable[WorldState], legs: Sequence[PlannedLeg]) -> List[Check]:
    """For each leg, where the player should be after it and what proves it."""
    result = []
    for i, (before, leg) in enumerate(zip(_beliefs(frozenset(start), legs), legs)):
        result.append(Check(i, leg.after, _proof(before, leg)))
    return result


def legs_from_path(planner: BeliefPlanner, path: Path) -> Optional[List[PlannedLeg]]:
    """A path's moves as planned legs: each straight run is split after each
    ledge hop (a ledge leg), and its rest is a wall leg if the player is held
    at its end, else an open leg of its length. None if the legs cannot be
    walked robustly (an open leg's error would run into a ledge, a door or an
    edge)."""
    legs: List[PlannedLeg] = []
    belief = frozenset({path.start})
    for direction, runs in _runs(path.moves):
        for kind, tiles in runs:
            leg = _run_leg(planner, belief, direction, kind, tiles)
            if leg is None:
                return None
            legs.append(leg)
            belief = leg.after
    return legs


#   ---- parts of a score ----

def _unprotected(leg: PlannedLeg, options: ScoreOptions) -> bool:
    return leg.end is LegEnd.OPEN or (leg.end is LegEnd.LEDGE and not options.ledges_localize)


def _margin(planner: BeliefPlanner, start: Belief, legs: Sequence[PlannedLeg], index: int, goal: Goal,
            options: ScoreOptions) -> int:
    """How many extra tiles of error leg `index` takes before the route
    fails (up to `max_margin`). A ledge leg counted as open has no error to
    widen, so its margin is 0."""
    if legs[index].end is not LegEnd.OPEN:
        return 0
    margin = 0
    for extra in range(1, options.max_margin + 1):
        walked = replay(planner, start, legs, (index, extra))
        if walked is None or not _reaches(walked, start, goal):
            break
        margin = extra
    return margin


def _localizations(start: Belief, legs: Sequence[PlannedLeg], options: ScoreOptions) -> int:
    count = 0
    for before, leg in zip(_beliefs(start, legs), legs):
        proves = leg.end is LegEnd.WALL or (leg.end is LegEnd.LEDGE and options.ledges_localize)
        if proves and len(leg.after) < len(before):
            count += 1
    return count


def _turns(legs: Sequence[PlannedLeg]) -> Tuple[int, int]:
    turns = turnarounds = 0
    for a, b in zip(legs, legs[1:]):
        if b.direction is not a.direction:
            turns += 1
            turnarounds += b.direction is a.direction.opposite
    return turns, turnarounds


def _grass(planner: BeliefPlanner, before: Belief, leg: PlannedLeg) -> int:
    """The most grass any state crosses on `leg`."""
    walked = _walk_leg(planner, before, leg, 0)
    if walked is None:
        return 0
    worst = 0
    for state in before:
        walk = planner.walk(state, leg.direction, limit=None if leg.end is not LegEnd.OPEN else leg.tiles,
                            stop_on_hop=leg.end is LegEnd.LEDGE)
        worst = max(worst, walk.grass)
    return worst


def _reaches(legs: Sequence[PlannedLeg], start: Belief, goal: Goal) -> bool:
    is_goal = goal if callable(goal) else (lambda state: state.place == goal)
    final = legs[-1].after if legs else start
    return all(is_goal(state) for state in final)


def _beliefs(start: Belief, legs: Sequence[PlannedLeg]) -> List[Belief]:
    """The belief before each leg."""
    return [start] + [leg.after for leg in legs[:-1]]


def _proof(before: Belief, leg: PlannedLeg) -> str:
    maps_before = {state.place.map for state in before}
    maps_after = {state.place.map for state in leg.after}
    if leg.end is LegEnd.WALL:
        return "wall bump"
    if leg.end is LegEnd.LEDGE:
        return "ledge landing"
    if maps_after != maps_before:
        return "map banner"
    return "none"


#   ---- paths to legs ----

def _runs(moves: Sequence[Move]):
    """(direction, [(kind, tiles), ...]) per straight run: a "ledge" part
    ending at each hop, then the rest as "rest"."""
    runs = []
    for move in moves:
        tiles = 2 if move.kind is MoveKind.HOP else 1
        if not runs or runs[-1][0] is not move.direction:
            runs.append((move.direction, []))
        parts = runs[-1][1]
        if not parts or parts[-1][0] == "ledge":
            parts.append(["rest", 0])
        parts[-1][1] += tiles
        if move.kind is MoveKind.HOP:
            parts[-1][0] = "ledge"
    return [(direction, [tuple(part) for part in parts]) for direction, parts in runs]


def _run_leg(planner: BeliefPlanner, belief: Belief, direction, kind: str, tiles: int) -> Optional[PlannedLeg]:
    if kind == "ledge":
        found = planner.ledge_leg(belief, direction)
    else:
        found = planner.wall_leg(belief, direction)
        if found is None or found[0].tiles != tiles:
            found = planner.open_leg(belief, direction, tiles)
    return None if found is None else found[0]
