"""Tests for pokenav.routing.localize: synchronizing a room, a corridor and
a region with no such sequence, and the robust planner inserting one."""

import unittest

from pokenav.geometry import Direction, Tile
from pokenav.maps.objects import is_corner
from pokenav.maps.textgrid import read
from pokenav.maps.world import Place, World
from pokenav.movement import WorldState
from pokenav.routing.belief import BeliefCosts, BeliefPlanner, LegEnd
from pokenav.routing.localize import anchor, synchronize, use_localization

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST

ROOM_TEXT = """\
#######
#.....#
#.....#
#.....#
#.....#
#######
"""


def at(x, y, name="M"):
    return WorldState(Place(name, Tile(x, y)))


def planner_for(text, costs=BeliefCosts()):
    return BeliefPlanner(World([read(text, name="M")]), costs)


def every_open_tile(planner, name="M"):
    grid = planner.world.grid(name)
    return [WorldState(Place(name, t)) for t in grid.tiles() if not grid.at(t).blocked]


class SynchronizeTest(unittest.TestCase):
    def test_a_room_goes_to_a_corner_in_two_legs(self):
        planner = planner_for(ROOM_TEXT)
        legs = synchronize(planner, every_open_tile(planner))
        self.assertEqual(len(legs), 2)
        self.assertTrue(all(leg.end is LegEnd.WALL for leg, _ in legs))
        corner = anchor(legs)
        self.assertTrue(is_corner(planner.world.grid("M"), corner.place.tile))

    def test_a_corridor_takes_one_leg(self):
        planner = planner_for("########\n#......#\n########\n")
        legs = synchronize(planner, every_open_tile(planner))
        self.assertEqual(len(legs), 1)
        self.assertIn(anchor(legs), {at(1, 1), at(6, 1)})

    def test_one_state_needs_nothing(self):
        planner = planner_for(ROOM_TEXT)
        self.assertEqual(synchronize(planner, [at(2, 2)]), [])
        self.assertIsNone(anchor([]))

    def test_rooms_that_look_the_same_cannot_be_told_apart(self):
        #   Two closed rooms, the same from inside: every leg sends each to its
        #   own corner, never to one tile.
        planner = planner_for("#######\n#..#..#\n#..#..#\n#######\n")
        self.assertIsNone(synchronize(planner, [at(1, 1), at(4, 1)]))

    def test_max_legs(self):
        #   A room needs two legs (one per wall of a corner), so one is not enough.
        planner = planner_for(ROOM_TEXT)
        self.assertIsNone(synchronize(planner, every_open_tile(planner), max_legs=1))


class InsertTest(unittest.TestCase):
    def test_the_planner_localizes_when_a_belief_grows_too_large(self):
        #   Anywhere in the 2 x 2 at the top left, to the corner, with at most
        #   one state after each leg: no single leg does it, but north then
        #   west does.
        start = [at(1, 1), at(2, 1), at(1, 2), at(2, 2)]
        tight = BeliefCosts(max_spread=1)
        self.assertIsNone(planner_for(ROOM_TEXT, tight).plan(start, Place("M", Tile(1, 1))))
        planner = use_localization(planner_for(ROOM_TEXT, tight))
        legs = planner.plan(start, Place("M", Tile(1, 1)))
        self.assertIsNotNone(legs)
        self.assertEqual(legs[-1].after, {at(1, 1)})
        self.assertTrue(all(leg.end is LegEnd.WALL for leg in legs))


if __name__ == "__main__":
    unittest.main()
