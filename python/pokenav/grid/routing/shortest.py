"""Shortest paths over the movement rules, with costs for turns and grass.

The search is Dijkstra over (where the player is, which way they face): each
press is one edge, costing its tiles (a ledge hop is 2), plus `turn` when it
changes direction and `grass` for each tall-grass tile it ends on. It runs
through a World, so a path can cross map edges and warps.

Costs are a parameter. A high grass weight makes a route go round the grass
at the price of turns; a high turn weight makes it cut through. What the
weights should be is decided by the routes they produce (see the Route 1
fixture in games/frlg/routes/).

    path = shortest_path(world, WorldState(Place("Route1", Tile(5, 3))),
                         goal=Place("Route1", Tile(5, 23)))
    [move.direction for move in path.moves]   # [SOUTH, SOUTH, ...]
    path.cost
"""

import enum
import heapq
import itertools
from typing import AbstractSet, Callable, Dict, List, NamedTuple, Optional, Tuple, Union

from pokenav.grid.geometry import CLOCKWISE, Direction
from pokenav.grid.maps.model import Behavior
from pokenav.grid.maps.world import Place, World
from pokenav.grid.movement import FLAT, ElevationRules, Hop, Moved, Warped, WorldState, world_step


class Costs(NamedTuple):
    """The weights of a path's cost. `tile` is per tile walked (a ledge hop
    walks 2); `turn` is added when a press goes another way than the last;
    `grass` is added per tall-grass tile entered (wild battles interrupt a
    walk); `warp` per warp taken."""

    tile: float = 1.0
    turn: float = 2.0
    #   With turn = 2, a grass weight of 5 or more keeps Route 1's
    #   Viridian-to-Pallet route out of the grass like the hand-drawn line;
    #   3 or less cuts through 10 grass tiles to save two turns.
    grass: float = 5.0
    warp: float = 1.0


class MoveKind(enum.Enum):
    STEP = "step"
    HOP = "hop"
    WARP = "warp"


class Move(NamedTuple):
    """One press: its direction, what it did, and where it left the player."""

    direction: Direction
    kind: MoveKind
    to: WorldState


class Path(NamedTuple):
    """A path from `start`: its moves in order and its total cost."""

    start: WorldState
    moves: List[Move]
    cost: float

    @property
    def end(self) -> WorldState:
        return self.moves[-1].to if self.moves else self.start

    def places(self) -> List[Place]:
        """Every place the path stands on, from the start."""
        return [self.start.place] + [move.to.place for move in self.moves]


Goal = Union[Place, Callable[[WorldState], bool]]

#   A search node: where the player is and which way they last moved (None
#   at the start, so the first press costs no turn).
_Node = Tuple[WorldState, Optional[Direction]]


def shortest_path(world: World, start: WorldState, goal: Goal, costs: Costs = Costs(),
                  rules: ElevationRules = FLAT, objects: AbstractSet[Place] = frozenset()) -> Optional[Path]:
    """The cheapest path from `start` to `goal` (a place, or a test on the
    player's state), or None if it cannot be reached."""
    is_goal = goal if callable(goal) else (lambda state: state.place == goal)
    order = itertools.count()
    start_node: _Node = (start, None)
    best: Dict[_Node, float] = {start_node: 0.0}
    came_from: Dict[_Node, Tuple[_Node, Move]] = {}
    frontier = [(0.0, next(order), start_node)]
    while frontier:
        cost, _, node = heapq.heappop(frontier)
        if cost > best.get(node, float("inf")):
            continue
        if is_goal(node[0]):
            return Path(start, _moves_to(node, came_from), cost)
        for move, move_cost in _moves(world, node, costs, rules, objects):
            next_node = (move.to, move.direction)
            next_cost = cost + move_cost
            if next_cost < best.get(next_node, float("inf")):
                best[next_node] = next_cost
                came_from[next_node] = (node, move)
                heapq.heappush(frontier, (next_cost, next(order), next_node))
    return None


def follow(world: World, start: WorldState, legs: List[Tuple[Direction, Place]], costs: Costs = Costs(),
           rules: ElevationRules = FLAT, objects: AbstractSet[Place] = frozenset(),
           max_presses: int = 1000) -> Path:
    """The path that walks each leg (a direction and the place it ends on) in
    turn, with its cost under `costs`: for scoring a route drawn by hand.
    Raises ValueError if a leg is stopped before its end."""
    moves: List[Move] = []
    cost = 0.0
    state, facing = start, None
    for direction, end in legs:
        while state.place != end:
            move = _as_move(direction, world_step(world, state, direction, rules, objects))
            if move is None or len(moves) >= max_presses:
                raise ValueError("leg %s to %s is stopped at %s" % (direction.name.lower(), end, state.place))
            cost += move_cost(world, state, move, costs) + (costs.turn if facing not in (None, direction) else 0.0)
            moves.append(move)
            state, facing = move.to, direction
    return Path(start, moves, cost)


def _moves(world: World, node: _Node, costs: Costs, rules: ElevationRules, objects: AbstractSet[Place]):
    """Each press from `node` that moves the player, with its cost."""
    state, facing = node
    for direction in CLOCKWISE:
        result = world_step(world, state, direction, rules, objects)
        move = _as_move(direction, result)
        if move is None:
            continue
        cost = move_cost(world, state, move, costs)
        if facing is not None and direction is not facing:
            cost += costs.turn
        yield move, cost


def _as_move(direction: Direction, result) -> Optional[Move]:
    if isinstance(result, Moved):
        return Move(direction, MoveKind.STEP, result.state)
    if isinstance(result, Hop):
        return Move(direction, MoveKind.HOP, result.state)
    if isinstance(result, Warped):
        return Move(direction, MoveKind.WARP, result.state)
    return None


def move_cost(world: World, before: WorldState, move: Move, costs: Costs) -> float:
    """What one move costs, before any turn."""
    if move.kind is MoveKind.WARP:
        return costs.warp
    tiles = 2 if move.kind is MoveKind.HOP else _tiles(before.place, move.to.place)
    grass = costs.grass if world.at(move.to.place).behavior is Behavior.TALL_GRASS else 0.0
    return tiles * costs.tile + grass


def _tiles(a: Place, b: Place) -> int:
    """Tiles between two places of one step: 1 across a map edge, else the
    distance (more than 1 after sliding on ice)."""
    return 1 if a.map != b.map else a.tile.manhattan(b.tile)


def _moves_to(node: _Node, came_from: Dict[_Node, Tuple[_Node, Move]]) -> List[Move]:
    moves = []
    while node in came_from:
        node, move = came_from[node]
        moves.append(move)
    moves.reverse()
    return moves
