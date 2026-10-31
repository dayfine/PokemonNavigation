"""Tests for pokenav.grid.routing.legs: the leg planner on a small made-up game
with walls, people, grass, a one-way ledge and a warp, and on BDSP's
Route 202."""

import unittest

from pokenav.games import bdsp
from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.schema import Warp
from pokenav.grid.maps.textgrid import parse
from pokenav.grid.maps.world import Place, World
from pokenav.grid.movement import WorldState
from pokenav.grid.routing.legs import LegKind, describe, held, join_legs, plan_legs
from pokenav.grid.routing.shortest import shortest_path

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST


def toy(text, warps=()):
    map_file = parse(text, name="Toy")
    map_file.warps = list(warps)
    return World([map_file])


def at(x, y, name="Toy"):
    return WorldState(Place(name, Tile(x, y)))


def plan(world, start, end, **kwargs):
    return plan_legs(world, at(*start), Place("Toy", Tile(*end)), **kwargs)


def text(legs):
    return "\n" + "\n".join(describe(leg) for leg in legs) if legs else " none"


class ToyGameTest(unittest.TestCase):
    def test_prefers_legs_that_end_at_a_wall(self):
        #   East then south ends in the open; south then east ends against
        #   the pillar. Both are 3 tiles and one turn.
        world = toy("......\n...#..\n......\n")
        legs = plan(world, (0, 0), (2, 1))
        self.assertEqual([(l.direction, l.to_wall) for l in legs], [(S, False), (E, True)], text(legs))

    def test_a_person_is_not_a_wall(self):
        world = World([parse("#####\n#..N#\n#####\n", name="Toy")])
        objects = {Place("Toy", Tile(3, 1))}
        legs = plan(world, (1, 1), (2, 1), objects=objects)
        self.assertEqual(len(legs), 1, text(legs))
        self.assertFalse(legs[0].to_wall)

    def test_avoids_grass(self):
        #   Straight through is 4 tiles with 3 grass; around is 8.
        world = toy(".....\n.,,,.\n.....\n")
        legs = plan(world, (0, 1), (4, 1))
        for leg in legs:
            self.assertFalse(leg.end.place.tile.y == 1 and 0 < leg.end.place.tile.x < 4, text(legs))

    def test_one_way_ledge(self):
        world = toy("#.#.#\n#v#.#\n#...#\n#####\n")
        down = plan(world, (1, 0), (1, 2))
        self.assertEqual([(l.direction, l.tiles) for l in down], [(S, 2)], text(down))
        self.assertIsNone(plan(world, (1, 2), (1, 0)))

    def test_a_warp_ends_its_leg(self):
        #   The warp on the left takes the player to the tile marked by the
        #   second warp record, on the right.
        world = toy("#######\n#W.#..#\n#..#..#\n#######\n",
                    warps=[Warp(Tile(1, 1), "Toy", 1), Warp(Tile(4, 1), "Toy", 0)])
        legs = plan(world, (2, 2), (5, 2))
        warp_legs = [leg for leg in legs if leg.warps]
        self.assertEqual(len(warp_legs), 1, text(legs))
        self.assertEqual(warp_legs[0].end.place, Place("Toy", Tile(4, 1)))
        after = legs[legs.index(warp_legs[0]) + 1]
        self.assertEqual(after.start.place, Place("Toy", Tile(4, 1)))

    def test_turns_to_face_the_goal(self):
        legs = plan(toy("....\n"), (0, 0), (2, 0), goal_facing=N)
        self.assertEqual((legs[-1].kind, legs[-1].direction), (LegKind.FACE, N), text(legs))
        no_turn = plan(toy("....\n"), (0, 0), (2, 0), goal_facing=E)
        self.assertEqual([l.kind for l in no_turn], [LegKind.WALK])

    def test_unreachable(self):
        self.assertIsNone(plan(toy(".#.\n"), (0, 0), (2, 0)))

    def test_join_legs_of_a_path(self):
        world = toy("......\n...#..\n......\n")
        path = shortest_path(world, at(0, 0), Place("Toy", Tile(5, 2)))
        legs = join_legs(world, path.start, path.moves)
        self.assertEqual(sum(leg.tiles for leg in legs), 7)
        self.assertEqual(legs[0].start, at(0, 0))
        self.assertEqual(legs[-1].end, at(5, 2))
        for a, b in zip(legs, legs[1:]):
            self.assertIsNot(a.direction, b.direction)
            self.assertEqual(a.end, b.start)


class Route202Test(unittest.TestCase):
    def test_catch_spot_to_jubilife(self):
        world = bdsp.story_world()
        start = WorldState(Place("Route 202", Tile(19, 22)))
        goal = Place("Route 202", Tile(15, 0))
        legs = plan_legs(world, start, goal)
        self.assertIsNotNone(legs)
        self.assertEqual(legs[-1].end.place, goal, text(legs))
        for leg in legs:
            self.assertEqual(leg.to_wall, held(world, leg.end, leg.direction), describe(leg))
        for a, b in zip(legs, legs[1:]):
            self.assertIsNot(a.direction, b.direction, text(legs))
        #   Ledges cannot be climbed, so the route goes round both by the
        #   gaps; no leg goes north over a ledge row.
        self.assertTrue(all(leg.tiles > 0 for leg in legs))


if __name__ == "__main__":
    unittest.main()
