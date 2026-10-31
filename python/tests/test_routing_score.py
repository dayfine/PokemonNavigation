"""Tests for pokenav.routing.score: hand-built routes ranked as expected,
margins, localizations, grass, the arrival checks, and (with
POKEFIRERED_DIR) Route 1 against the hand-drawn line."""

import copy
import json
import os
import unittest

from pokenav.games import frlg
from pokenav.geometry import Direction, Tile
from pokenav.maps.model import LEDGE_DIRECTION, WALL
from pokenav.maps.schema import Connection
from pokenav.maps.textgrid import parse
from pokenav.maps.world import Place, World
from pokenav.movement import WorldState
from pokenav.routing.belief import BeliefCosts, BeliefPlanner, LegEnd, OpenLegError
from pokenav.routing.score import (
    WEIGHTS, ScoreOptions, checks, legs_from_path, plan_ranked, propose, rank, replay, score,
)
from pokenav.routing.shortest import Costs, follow, shortest_path

from tests.paths import GAMES

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST

#   Open legs land exactly here, so a route's risk comes only from margins.
EXACT = BeliefCosts(error=OpenLegError(base=0, exact_up_to=99))

#   A room with a pillar at (5, 3).
ROOM = World([parse("""\
#########
#.......#
#.......#
#....#..#
#########
""", name="Room")])


def at(x, y, name="Room"):
    return WorldState(Place(name, Tile(x, y)))


def legs(planner, start, steps):
    """Planned legs from (kind, direction[, tiles]) steps."""
    belief = frozenset({start})
    out = []
    for step in steps:
        kind, direction = step[0], step[1]
        if kind == "wall":
            leg, _ = planner.wall_leg(belief, direction)
        elif kind == "ledge":
            leg, _ = planner.ledge_leg(belief, direction)
        else:
            leg, _ = planner.open_leg(belief, direction, step[2])
        out.append(leg)
        belief = leg.after
    return out


class RankTest(unittest.TestCase):
    def setUp(self):
        self.planner = BeliefPlanner(ROOM, EXACT)
        self.start = at(2, 1)
        self.goal = Place("Room", Tile(4, 3))

    def test_wall_anchored_with_one_more_turn_beats_short_but_open(self):
        routes = {
            #   East 2 in the open, then south to the bottom wall: one turn,
            #   but a tile long ends beside the pillar instead.
            "short but open": legs(self.planner, self.start, [("open", E, 2), ("wall", S)]),
            #   West, south and east, each to a wall: two turns, no doubt.
            "wall-anchored": legs(self.planner, self.start, [("wall", W), ("wall", S), ("wall", E)]),
        }
        ranked = rank(self.planner, [self.start], routes, self.goal)
        self.assertEqual([r.name for r in ranked], ["wall-anchored", "short but open"])
        wall, open_ = ranked[0].score, ranked[1].score
        self.assertEqual((wall.risk, wall.turns), (0, 2))
        self.assertEqual((open_.risk, open_.turns), (1.0, 1))

    def test_weights_can_put_turns_first(self):
        routes = {
            "short but open": legs(self.planner, self.start, [("open", E, 2), ("wall", S)]),
            "wall-anchored": legs(self.planner, self.start, [("wall", W), ("wall", S), ("wall", E)]),
        }
        options = ScoreOptions(weights={"risk": 1, "turns": 5})
        self.assertEqual(rank(self.planner, [self.start], routes, self.goal, options)[0].name, "short but open")

    def test_a_route_that_misses_the_goal_is_dropped(self):
        routes = {"wrong": legs(self.planner, self.start, [("wall", S)])}
        self.assertEqual(rank(self.planner, [self.start], routes, self.goal), [])

    def test_margin(self):
        #   Any bottom-row tile left of the pillar will do: the open leg east
        #   can go up to 2 tiles long or 1 short before the route fails.
        goal = lambda s: s.place.tile.y == 3 and s.place.tile.x <= 4
        route = legs(self.planner, at(1, 1), [("open", E, 2), ("wall", S)])
        result = score(self.planner, [at(1, 1)], route, goal, ScoreOptions(max_margin=3))
        self.assertAlmostEqual(result.risk, 1 / (1 + 1))

    def test_localizations_and_grass(self):
        world = World([parse("#####\n#.,.#\n#...#\n#####\n", name="Room")])
        planner = BeliefPlanner(world, EXACT)
        #   Anywhere in the 2 x 2 at the top left: north to the wall, then
        #   west to the wall, each shrinking the belief.
        start = [at(1, 1), at(2, 1), at(1, 2), at(2, 2)]
        route = [planner.wall_leg(frozenset(start), N)[0]]
        route.append(planner.wall_leg(route[0].after, W)[0])
        goal = Place("Room", Tile(1, 1))
        self.assertEqual(score(planner, start, route, goal).localizations, 1)    # the first is free
        self.assertEqual(score(planner, start, route, goal, ScoreOptions(free_localizations=0)).localizations, 2)
        self.assertEqual(score(planner, start, route, goal).grass, 1)       # (2, 2) north crosses (2, 1)
        across = legs(planner, at(1, 1), [("wall", E)])
        self.assertEqual(score(planner, [at(1, 1)], across, Place("Room", Tile(3, 1))).grass, 1)

    def test_ledges_localize(self):
        world = World([parse("#...#\n#...#\n#vvv#\n#...#\n#####\n", name="Room")])
        planner = BeliefPlanner(world, EXACT)
        route = legs(planner, at(2, 0), [("ledge", S)])
        goal = Place("Room", Tile(2, 3))
        self.assertEqual(score(planner, [at(2, 0)], route, goal).risk, 0)
        self.assertEqual(score(planner, [at(2, 0)], route, goal, ScoreOptions(ledges_localize=False)).risk, 1)


class ChecksTest(unittest.TestCase):
    def test_each_leg_says_how_it_is_proven(self):
        north = parse("....\n....\n", name="North")
        north.connections = [Connection(S, "South", 0)]
        south = parse("....\n#vv#\n....\n....\n####\n", name="South")
        south.connections = [Connection(N, "North", 0)]
        world = World([north, south])
        planner = BeliefPlanner(world, EXACT)
        start = WorldState(Place("North", Tile(1, 0)))
        route = legs(planner, start, [("open", S, 2), ("ledge", S), ("wall", S)])
        self.assertEqual([c.proof for c in checks([start], route)], ["map banner", "ledge landing", "wall bump"])
        self.assertEqual(checks([start], route)[1].expected, {WorldState(Place("South", Tile(1, 2)))})

    def test_replay_and_paths(self):
        planner = BeliefPlanner(ROOM, EXACT)
        path = shortest_path(ROOM, at(1, 1), Place("Room", Tile(4, 3)))
        route = legs_from_path(planner, path)
        self.assertEqual(route[-1].after, {at(4, 3)})
        self.assertEqual(replay(planner, [at(1, 1)], route), route)


POKEFIRERED = os.environ.get("POKEFIRERED_DIR", "")
ROUTE1_FIXTURE = os.path.join(GAMES, "frlg", "routes", "viridian_to_pallet.json")


def _place(value):
    name, x, y = value
    return Place(name, Tile(x, y))


@unittest.skipUnless(POKEFIRERED and os.path.isdir(POKEFIRERED), "set POKEFIRERED_DIR to a pokefirered checkout")
class Route1Test(unittest.TestCase):
    """Viridian City to Pallet Town, ranked against the hand-drawn line."""

    @classmethod
    def setUpClass(cls):
        from pokenav.maps.pret import Checkout
        with open(ROUTE1_FIXTURE) as f:
            cls.fixture = json.load(f)
        cls.maps = [Checkout(POKEFIRERED, frlg.PRET).load_map(name) for name in cls.fixture["maps"]]
        cls.world = World(cls.maps)
        cls.planner = BeliefPlanner(cls.world, BeliefCosts(error=frlg.OPEN_LEG_ERROR), frlg.ELEVATION_RULES)
        cls.start = WorldState(_place(cls.fixture["start"]), 3)
        cls.goal = _place(cls.fixture["waypoints"][-1]["place"])
        drawn = [(Direction.parse(w["direction"]), _place(w["place"])) for w in cls.fixture["waypoints"]]
        cls.drawn = legs_from_path(cls.planner, follow(cls.world, cls.start, drawn, Costs(), frlg.ELEVATION_RULES))

    def turn_legs(self, route):
        """(direction, end of the run) for each run of legs in one direction."""
        runs = []
        for leg in route:
            (end,) = leg.after
            if runs and runs[-1][0] is leg.direction:
                runs[-1] = (leg.direction, end.place)
            else:
                runs.append((leg.direction, end.place))
        return runs

    def test_with_a_grass_weight_the_top_route_has_the_drawn_shape(self):
        routes = propose(self.planner, self.start, self.goal)
        drawn = score(self.planner, [self.start], self.drawn, self.goal)
        for grass in (2, 5, 20):
            options = ScoreOptions(weights=dict(WEIGHTS, grass=grass))
            best = rank(self.planner, [self.start], routes, self.goal, options)[0]
            with self.subTest(grass=grass):
                self.assertEqual((best.score.risk, best.score.turns, best.score.grass),
                                 (drawn.risk, drawn.turns, drawn.grass))
                self._check_shape(best.legs)

    def test_without_one_the_top_route_cuts_through_grass(self):
        best = plan_ranked(self.planner, self.start, self.goal, ScoreOptions(weights=dict(WEIGHTS, grass=0.5)))[0]
        self.assertGreater(best.score.grass, self.fixture["expected"]["grass_tiles"])
        lexicographic = plan_ranked(self.planner, self.start, self.goal)[0]
        self.assertGreater(lexicographic.score.grass, self.fixture["expected"]["grass_tiles"])

    def _check_shape(self, route):
        """The drawn line's leg directions, ledge drops, and rows (within the
        accepted ones); vertical legs' columns tie, see docs/ROUTING.md."""
        runs = self.turn_legs(route)
        waypoints = self.fixture["waypoints"]
        self.assertEqual([d for d, _ in runs], [Direction.parse(w["direction"]) for w in waypoints])
        for i, ((direction, end), waypoint) in enumerate(zip(runs, waypoints)):
            if direction.is_vertical:
                continue
            rows = [(p.map, p.tile.y) for p in map(_place, [waypoint["place"]] + waypoint.get("or", []))]
            self.assertIn((end.map, end.tile.y), rows, "leg %d" % (i + 1))
        self.assertEqual(sum(1 for leg in route if leg.end is LegEnd.LEDGE),
                         self.fixture["expected"]["ledge_drops"])

    def test_the_old_zigzag_ranks_below_the_drawn_line(self):
        #   The old planner did not use ledges and weighed grass at 20 a tile.
        no_ledges = []
        for map_file in self.maps:
            walled = copy.deepcopy(map_file)
            for tile in walled.grid.tiles():
                if walled.grid.at(tile).behavior in LEDGE_DIRECTION:
                    walled.grid.set(tile, WALL)
            no_ledges.append(walled)
        path = shortest_path(World(no_ledges), self.start, self.goal, Costs(grass=20), frlg.ELEVATION_RULES)
        zigzag = legs_from_path(self.planner, path)
        ranked = rank(self.planner, [self.start], {"drawn": self.drawn, "zigzag": zigzag}, self.goal)
        self.assertEqual([r.name for r in ranked], ["drawn", "zigzag"])
        self.assertGreater(ranked[1].score.turns, ranked[0].score.turns)
        self.assertGreater(ranked[1].score.grass, ranked[0].score.grass)
        #   Without ledges as localization, the drawn line loses its edge: each
        #   drop becomes an unprotected move.
        old = score(self.planner, [self.start], self.drawn, self.goal, ScoreOptions(ledges_localize=False))
        new = score(self.planner, [self.start], self.drawn, self.goal)
        self.assertEqual(old.risk - new.risk, self.fixture["expected"]["ledge_drops"])


if __name__ == "__main__":
    unittest.main()
