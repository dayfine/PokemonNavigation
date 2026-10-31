"""Legs: a walk as straight runs, "hold east for 4 tiles, then south".

A bot walks by holding a direction until it has gone far enough or something
stops it. A leg that ends against a wall is safe: the player stops there
however long the stick is held, and can hold again after an interruption. A
leg that ends in the open depends on timing. So the leg planner searches
like `routing.shortest`, but charges `open_stop` for every leg that ends
where the player could have kept going, and prefers legs that end at a wall.

    legs = plan_legs(world, start, goal=Place("Route 202", Tile(30, 19)))
    for leg in legs:
        print(describe(leg))    # "walk east 11 (to wall) -> Route 202 (30, 22)"

`join_legs` turns any path (a list of moves) into legs, and a goal facing
adds a FACE leg at the end (turning without a step).
"""

import enum
import heapq
import itertools
from typing import AbstractSet, Dict, List, NamedTuple, Optional, Tuple

from pokenav.geometry import CLOCKWISE, Direction
from pokenav.maps.world import Place, World
from pokenav.movement import FLAT, HOLDING_REASONS, Blocked, ElevationRules, WorldState, world_step
from pokenav.routing.shortest import Costs, Goal, Move, MoveKind, as_move, move_cost


class LegKind(enum.Enum):
    WALK = "walk"    #   hold `direction` for `tiles` tiles
    FACE = "face"    #   turn to `direction` without moving


class Leg(NamedTuple):
    """One straight run, or a turn on the spot."""

    kind: LegKind
    direction: Direction
    tiles: int              #   tiles walked; a ledge hop counts 2
    to_wall: bool           #   holding on keeps the player at `end`
    warps: bool             #   the last step took a warp
    start: WorldState
    end: WorldState


class LegCosts(NamedTuple):
    """Path costs, plus `open_stop` for each leg that ends where the player
    could keep going: it has to be timed, and an interruption leaves the
    player at a guess."""

    path: Costs = Costs()
    open_stop: float = 8.0


def describe(leg: Leg) -> str:
    """A leg in words, for logs and test messages."""
    if leg.kind is LegKind.FACE:
        return "face %s" % leg.direction.name.lower()
    flags = (" (to wall)" if leg.to_wall else "") + (" (warp)" if leg.warps else "")
    return "walk %s %d%s -> %s" % (leg.direction.name.lower(), leg.tiles, flags, leg.end.place)


def held(world: World, state: WorldState, direction: Direction, rules: ElevationRules = FLAT,
         objects: AbstractSet[Place] = frozenset()) -> bool:
    """Whether holding `direction` keeps the player at `state`, across maps."""
    result = world_step(world, state, direction, rules, objects)
    return isinstance(result, Blocked) and result.reason in HOLDING_REASONS


def join_legs(world: World, start: WorldState, moves: List[Move], rules: ElevationRules = FLAT,
              objects: AbstractSet[Place] = frozenset()) -> List[Leg]:
    """The legs of a list of moves: consecutive moves in one direction join,
    except that a warp ends its leg."""
    legs: List[Leg] = []
    before = start
    for move in moves:
        tiles = 2 if move.kind is MoveKind.HOP else 1
        last = legs[-1] if legs else None
        if last is not None and last.direction is move.direction and not last.warps:
            legs[-1] = last._replace(tiles=last.tiles + tiles, end=move.to)
        else:
            legs.append(Leg(LegKind.WALK, move.direction, tiles, False, False, before, move.to))
        warped = move.kind is MoveKind.WARP
        to_wall = not warped and held(world, move.to, move.direction, rules, objects)
        legs[-1] = legs[-1]._replace(warps=warped, to_wall=to_wall)
        before = move.to
    return legs


#   A search node: where the player is, which way they face (None: not
#   known), and whether they are mid-leg and could keep going.
class _Node(NamedTuple):
    state: WorldState
    facing: Optional[Direction]
    moving: bool


def plan_legs(world: World, start: WorldState, goal: Goal, start_facing: Optional[Direction] = None,
              goal_facing: Optional[Direction] = None, costs: LegCosts = LegCosts(),
              rules: ElevationRules = FLAT, objects: AbstractSet[Place] = frozenset()) -> Optional[List[Leg]]:
    """The cheapest legs from `start` to `goal`, ending facing `goal_facing`
    if given, or None if the goal cannot be reached."""
    search = _LegSearch(world, costs, rules, objects, goal, goal_facing)
    end, moves = search.run(_Node(start, start_facing, False))
    if end is None:
        return None
    legs = join_legs(world, start, moves, rules, objects)
    if goal_facing is not None and end.facing is not goal_facing:
        legs.append(Leg(LegKind.FACE, goal_facing, 0, False, False, end.state, end.state))
    return legs


class _LegSearch:
    """Dijkstra over nodes; the cost of a node at the goal includes stopping
    there and turning to the goal facing."""

    def __init__(self, world, costs, rules, objects, goal, goal_facing):
        self.world = world
        self.costs = costs
        self.rules = rules
        self.objects = objects
        self.is_goal = goal if callable(goal) else (lambda state: state.place == goal)
        self.goal_facing = goal_facing

    def run(self, first: _Node) -> Tuple[Optional[_Node], List[Move]]:
        order = itertools.count()
        distance: Dict[_Node, float] = {first: 0.0}
        came_from: Dict[_Node, Tuple[_Node, Move]] = {}
        queue = [(0.0, next(order), first)]
        best_end, best_total = None, float("inf")
        while queue:
            cost, _, node = heapq.heappop(queue)
            if cost > distance.get(node, float("inf")) or cost >= best_total:
                continue
            if self.is_goal(node.state):
                total = cost + self._arrival_cost(node)
                if total < best_total:
                    best_end, best_total = node, total
                continue
            for next_node, move, step_cost in self._expand(node):
                if cost + step_cost < distance.get(next_node, float("inf")):
                    distance[next_node] = cost + step_cost
                    came_from[next_node] = (node, move)
                    heapq.heappush(queue, (cost + step_cost, next(order), next_node))
        return best_end, _moves_to(best_end, came_from) if best_end else []

    def _expand(self, node: _Node):
        for direction in CLOCKWISE:
            move = as_move(direction, world_step(self.world, node.state, direction, self.rules, self.objects))
            if move is None:
                continue
            cost = move_cost(self.world, node.state, move, self.costs.path)
            if node.facing is not None and direction is not node.facing:
                cost += self.costs.path.turn + self._stop_cost(node)
            yield _Node(move.to, direction, move.kind is not MoveKind.WARP), move, cost

    def _stop_cost(self, node: _Node) -> float:
        """What ending a leg at `node` costs: nothing at a wall or after a
        warp, `open_stop` in the open."""
        if not node.moving or held(self.world, node.state, node.facing, self.rules, self.objects):
            return 0.0
        return self.costs.open_stop

    def _arrival_cost(self, node: _Node) -> float:
        cost = self._stop_cost(node)
        if self.goal_facing is not None and node.facing is not self.goal_facing:
            cost += self.costs.path.turn
        return cost


def _moves_to(node: _Node, came_from: Dict[_Node, Tuple[_Node, Move]]) -> List[Move]:
    moves = []
    while node in came_from:
        node, move = came_from[node]
        moves.append(move)
    moves.reverse()
    return moves
