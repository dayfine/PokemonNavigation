"""Tests for pokenav.grid.routing.localize: synchronizing a room, a corridor and
a region with no such sequence, and the robust planner inserting one."""

import unittest

from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.objects import is_corner
from pokenav.grid.maps.textgrid import parse
from pokenav.grid.maps.world import Place, World
from pokenav.grid.movement import WorldState
from pokenav.grid.routing.belief import BeliefCosts, BeliefPlanner, LegEnd
from pokenav.grid.routing.localize import anchor, synchronize, use_localization
from pokenav.physics.model import TileError

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
    return BeliefPlanner(World([parse(text, name="M")]), costs)


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
    #   A street that runs off the known map at the east, with a person at
    #   (5, 1) and a nook at (7..9, 2). From (6, 1), east of the person, no
    #   wall leg is allowed: west is the person, east the unknown, north and
    #   south walls at once. A hold east may miss a tile; two wall legs then
    #   bring the belief to the nook's corner.
    STREET_TEXT = """\
###########
#....N....?
#.....#...#
###########
"""
    PERSON = frozenset({Place("M", Tile(5, 1))})

    def planner(self, costs):
        return BeliefPlanner(World([parse(self.STREET_TEXT, name="M")]), costs, objects=self.PERSON)

    def test_the_planner_localizes_when_a_belief_grows_too_large(self):
        #   With at most one state after each leg, the hold's two states end
        #   the search; with localization they are walked to the corner.
        start, goal = at(6, 1), Place("M", Tile(9, 2))
        tight = BeliefCosts(max_spread=1, error=TileError(overshoot=1))
        self.assertIsNone(self.planner(tight).plan(start, goal))
        planner = use_localization(self.planner(tight))
        legs = planner.plan(start, goal)
        self.assertIsNotNone(legs)
        self.assertEqual([leg.end for leg in legs], [LegEnd.OPEN, LegEnd.WALL, LegEnd.WALL])
        self.assertGreater(len(legs[0].after), tight.max_spread)
        self.assertEqual(legs[-1].after, {at(9, 2)})

if __name__ == "__main__":
    unittest.main()
