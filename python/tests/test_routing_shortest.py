"""Tests for pokenav.routing.shortest: optimal paths on small maps, ledges,
elevation, warps, unreachable goals, the grass weight, and Route 1 from a
real pokefirered checkout when POKEFIRERED_DIR is set."""

import json
import os
import unittest

from pokenav.games import frlg
from pokenav.geometry import Direction, Tile
from pokenav.maps.model import Behavior
from pokenav.maps.textgrid import parse
from pokenav.maps.world import Place, World
from pokenav.movement import WorldState
from pokenav.routing.shortest import Costs, MoveKind, follow, shortest_path

from tests.paths import GAMES
from tests.test_maps_world import two_towns

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST


def world_of(text, name="M"):
    return World([parse(text, name=name)])


def at(x, y, name="M", elevation=0):
    return WorldState(Place(name, Tile(x, y)), elevation)


def legs_of(path):
    """(direction, end place) for each run of moves in one direction."""
    legs = []
    for move in path.moves:
        if legs and legs[-1][0] is move.direction:
            legs[-1] = (move.direction, move.to.place)
        else:
            legs.append((move.direction, move.to.place))
    return legs


ROOM = """\
#######
#.....#
#.#.#.#
#.....#
#######
"""


class ShortestTest(unittest.TestCase):
    def test_straight_line(self):
        path = shortest_path(world_of(ROOM), at(1, 1), Place("M", Tile(5, 1)))
        self.assertEqual([m.direction for m in path.moves], [E] * 4)
        self.assertEqual(path.cost, 4)
        self.assertEqual(path.end, at(5, 1))

    def test_turns_cost(self):
        #   (1, 1) to (5, 3): 6 tiles any way; one turn is cheapest.
        path = shortest_path(world_of(ROOM), at(1, 1), Place("M", Tile(5, 3)))
        self.assertEqual(len(legs_of(path)), 2)
        self.assertEqual(path.cost, 6 + Costs().turn)
        zigzag_free = shortest_path(world_of(ROOM), at(1, 1), Place("M", Tile(5, 3)), Costs(turn=0))
        self.assertEqual(zigzag_free.cost, 6)

    def test_start_is_goal(self):
        path = shortest_path(world_of(ROOM), at(1, 1), Place("M", Tile(1, 1)))
        self.assertEqual((path.moves, path.cost), ([], 0))

    def test_goal_as_a_test(self):
        path = shortest_path(world_of(ROOM), at(1, 1), lambda s: s.place.tile.y == 3)
        self.assertEqual(path.end.place.tile.y, 3)
        self.assertEqual(len(path.moves), 2)

    def test_ledges_are_one_way(self):
        world = world_of("#.#\n#v#\n#.#\n")
        down = shortest_path(world, at(1, 0), Place("M", Tile(1, 2)))
        self.assertEqual([m.kind for m in down.moves], [MoveKind.HOP])
        self.assertEqual(down.cost, 2)
        self.assertIsNone(shortest_path(world, at(1, 2), Place("M", Tile(1, 0))))

    def test_elevation_needs_a_transition(self):
        world = world_of("...\n.#.\n...\n// Elevation:\n// 304\n// 304\n// 444\n")
        self.assertIsNone(shortest_path(world, at(0, 0, elevation=3), Place("M", Tile(2, 0))))
        path = shortest_path(world, at(0, 0, elevation=3), Place("M", Tile(2, 0)), rules=frlg.ELEVATION_RULES)
        self.assertEqual(path.end.place, Place("M", Tile(2, 0)))

    def test_objects_block(self):
        world = world_of(".....\n")
        self.assertIsNone(shortest_path(world, at(0, 0), Place("M", Tile(4, 0)), objects={Place("M", Tile(2, 0))}))

    def test_through_a_door_pair_and_across_maps(self):
        world = two_towns()
        path = shortest_path(world, at(1, 1, "House"), Place("North", Tile(4, 0)))
        kinds = [m.kind for m in path.moves]
        self.assertIn(MoveKind.WARP, kinds)
        self.assertEqual([p.map for p in path.places()][:2], ["House", "South"])
        self.assertEqual(path.end.place, Place("North", Tile(4, 0)))

    def test_unreachable(self):
        self.assertIsNone(shortest_path(world_of("..#..\n"), at(0, 0), Place("M", Tile(4, 0))))

    def test_grass_weight(self):
        #   Straight through 3 grass tiles, or round them with 4 turns and 4
        #   more tiles.
        world = world_of("""\
#######
#.,,,.#
#.###.#
#.....#
#######
""")
        goal = Place("M", Tile(5, 1))
        through = shortest_path(world, at(1, 1), goal, Costs(grass=0))
        self.assertEqual(len(through.moves), 4)
        around = shortest_path(world, at(1, 1), goal, Costs(grass=10))
        self.assertEqual(len(around.moves), 8)
        self.assertEqual(legs_of(around), [(S, Place("M", Tile(1, 3))), (E, Place("M", Tile(5, 3))),
                                           (N, Place("M", Tile(5, 1)))])

    def test_follow_a_drawn_route(self):
        path = follow(world_of(ROOM), at(1, 1), [(E, Place("M", Tile(3, 1))), (S, Place("M", Tile(3, 3)))])
        self.assertEqual(path.cost, 4 + Costs().turn)
        with self.assertRaises(ValueError):
            follow(world_of(ROOM), at(1, 1), [(S, Place("M", Tile(1, 9)))])


POKEFIRERED = os.environ.get("POKEFIRERED_DIR", "")
ROUTE1_FIXTURE = os.path.join(GAMES, "frlg", "routes", "viridian_to_pallet.json")


@unittest.skipUnless(POKEFIRERED and os.path.isdir(POKEFIRERED), "set POKEFIRERED_DIR to a pokefirered checkout")
class Route1Test(unittest.TestCase):
    """Viridian City to Pallet Town against the hand-drawn line."""

    @classmethod
    def setUpClass(cls):
        from pokenav.maps.pret import Checkout
        with open(ROUTE1_FIXTURE) as f:
            cls.fixture = json.load(f)
        cls.world = Checkout(POKEFIRERED, frlg.PRET).load_world(cls.fixture["maps"])
        name, x, y = cls.fixture["start"]
        cls.start = WorldState(Place(name, Tile(x, y)), 3)
        cls.waypoints = cls.fixture["waypoints"]
        cls.goal = _place(cls.waypoints[-1]["place"])

    def plan(self, costs):
        return shortest_path(self.world, self.start, self.goal, costs, frlg.ELEVATION_RULES)

    def test_the_drawn_line_can_be_walked(self):
        legs = [(Direction.parse(w["direction"]), _place(w["place"])) for w in self.waypoints]
        path = follow(self.world, self.start, legs, Costs(), frlg.ELEVATION_RULES)
        expected = self.fixture["expected"]
        self.assertEqual(sum(1 for m in path.moves if m.kind is MoveKind.HOP), expected["ledge_drops"])
        self.assertEqual(_grass_tiles(self.world, path), expected["grass_tiles"])

    def test_grass_weight_keeps_the_drawn_shape(self):
        for turn, grass in [(1, 3), (2, 5), (2, 20), (3, 10)]:
            path = self.plan(Costs(turn=turn, grass=grass))
            with self.subTest(turn=turn, grass=grass):
                self._check_shape(path)

    def test_low_grass_weight_cuts_through_the_grass(self):
        path = self.plan(Costs(turn=2, grass=3))
        self.assertGreater(_grass_tiles(self.world, path), self.fixture["expected"]["grass_tiles"])

    def _check_shape(self, path):
        """Same legs and directions, ledge drops and grass as the drawn line;
        each horizontal leg on the drawn row (or an accepted one); the first
        and last vertical legs on the drawn column. Legs 3 and 5 may run in
        another column: for the shortest path all columns there tie."""
        legs = legs_of(path)
        expected = self.fixture["expected"]
        self.assertEqual([d for d, _ in legs], [Direction.parse(w["direction"]) for w in self.waypoints])
        self.assertEqual(sum(1 for m in path.moves if m.kind is MoveKind.HOP), expected["ledge_drops"])
        self.assertEqual(_grass_tiles(self.world, path), expected["grass_tiles"])
        for i, ((direction, end), waypoint) in enumerate(zip(legs, self.waypoints)):
            accepted = [_place(p) for p in [waypoint["place"]] + waypoint.get("or", [])]
            if direction.is_vertical and i not in (0, len(legs) - 2):
                continue
            line = (lambda p: (p.map, p.tile.x)) if direction.is_vertical else (lambda p: (p.map, p.tile.y))
            self.assertIn(line(end), [line(p) for p in accepted], "leg %d ends at %s" % (i + 1, end))


def _place(value):
    name, x, y = value
    return Place(name, Tile(x, y))


def _grass_tiles(world, path):
    return sum(1 for m in path.moves if world.at(m.to.place).behavior is Behavior.TALL_GRASS)


if __name__ == "__main__":
    unittest.main()
