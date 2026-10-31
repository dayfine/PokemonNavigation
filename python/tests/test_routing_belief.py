"""Tests for pokenav.routing.belief: walls and ledges collapse beliefs, open
legs spread them, doors and edges are avoided, and robust plans on BDSP's
story maps and (with POKEFIRERED_DIR) FRLG's Route 1."""

import os
import unittest

from pokenav.games import bdsp, frlg
from pokenav.geometry import Direction, Tile
from pokenav.maps.textgrid import parse
from pokenav.maps.world import Place, World
from pokenav.movement import WorldState
from pokenav.routing.belief import (
    BeliefCosts, BeliefPlanner, LegEnd, OpenLegError, describe, plan_belief,
)

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST

ROOM = World([parse("""\
#######
#.....#
#.....#
#.....#
#.....#
#######
""", name="Room")])


def at(x, y, name="Room", elevation=0):
    return WorldState(Place(name, Tile(x, y)), elevation)


def text(legs):
    return "\n" + "\n".join(describe(leg) for leg in legs) if legs else " none"


class OpenLegErrorTest(unittest.TestCase):
    def test_spread_grows_with_length(self):
        error = OpenLegError()
        self.assertEqual([error.spread(n) for n in (1, 4, 5, 9, 10)], [1, 1, 2, 2, 3])
        self.assertEqual(OpenLegError(exact_up_to=2).spread(2), 0)


class BeliefTest(unittest.TestCase):
    def test_walls_collapse_a_row(self):
        start = [at(x, 1) for x in range(1, 6)]
        legs = plan_belief(ROOM, start, Place("Room", Tile(1, 4)))
        self.assertIsNotNone(legs)
        self.assertTrue(all(leg.end is LegEnd.WALL for leg in legs), text(legs))
        self.assertEqual(legs[-1].after, {at(1, 4)})

    def test_open_legs_spread(self):
        #   The middle of the room is reached only by an open leg, which may go
        #   a tile short or long: no plan, unless short legs land exactly.
        self.assertIsNone(plan_belief(ROOM, [at(1, 1)], Place("Room", Tile(3, 2))))
        exact = BeliefCosts(error=OpenLegError(exact_up_to=2))
        legs = plan_belief(ROOM, [at(1, 1)], Place("Room", Tile(3, 2)), exact)
        self.assertEqual(legs[-1].after, {at(3, 2)}, text(legs))

    def test_open_leg_reports_its_spread(self):
        planner = BeliefPlanner(ROOM)
        legs = {leg.tiles: leg for leg, _ in planner.open_legs(frozenset({at(1, 2)}), E)}
        self.assertEqual(legs[2].after, {at(2, 2), at(3, 2), at(4, 2)})
        #   Near the wall the spread is cut short by it.
        self.assertEqual(legs[4].after, {at(4, 2), at(5, 2)})

    def test_goal_region(self):
        legs = plan_belief(ROOM, [at(1, 2)], lambda s: s.place.tile.y == 4 and 2 <= s.place.tile.x <= 4,
                           BeliefCosts(max_spread=3))
        self.assertIsNotNone(legs)
        for state in legs[-1].after:
            self.assertTrue(state.place.tile.y == 4 and 2 <= state.place.tile.x <= 4, text(legs))

    def test_avoids_doors(self):
        #   North from (2, 3) would walk into the door; the plan goes round.
        world = World([parse("##D###\n#....#\n#....#\n#....#\n######\n", name="Room")])
        legs = plan_belief(world, [at(2, 3)], Place("Room", Tile(1, 1)))
        self.assertIsNotNone(legs)
        self.assertNotIn((N, frozenset({at(2, 1)})), [(l.direction, l.after) for l in legs])
        planner = BeliefPlanner(world)
        self.assertIsNone(planner.wall_leg(frozenset({at(2, 3)}), N))
        self.assertEqual(legs[-1].after, {at(1, 1)}, text(legs))

    def test_a_ledge_drop_pins_the_row(self):
        world = World([parse("""\
#.....#
#.....#
#vvvvv#
#.....#
#.....#
""", name="Field")])
        planner = BeliefPlanner(world)
        above = frozenset({at(2, 0, "Field"), at(2, 1, "Field")})
        leg, _ = planner.ledge_leg(above, S)
        self.assertEqual(leg.after, {at(2, 3, "Field")})
        self.assertIs(leg.end, LegEnd.LEDGE)
        #   An open leg over the ledge is refused: the hop's time is fixed.
        self.assertEqual([l.tiles for l, _ in planner.open_legs(frozenset({at(2, 0, "Field")}), S)], [])
        self.assertIsNone(planner.ledge_leg(frozenset({at(2, 3, "Field")}), S))

    def test_max_spread(self):
        start = [at(x, y) for x in range(1, 6) for y in range(1, 5)]
        #   No single leg brings 20 tiles down to 3: a corner takes two.
        self.assertIsNone(plan_belief(ROOM, start, Place("Room", Tile(5, 4)), BeliefCosts(max_spread=3)))
        legs = plan_belief(ROOM, start, Place("Room", Tile(5, 4)), BeliefCosts(max_spread=5))
        self.assertTrue(all(len(leg.after) <= 5 for leg in legs), text(legs))


class StoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = bdsp.story_world()

    def test_route202_catch_spot_to_save_spot(self):
        start = [WorldState(Place("Route 202", Tile(19, 22)))]
        goal = Place("Route 202", Tile(30, 19))
        legs = plan_belief(self.world, start, goal)
        self.assertIsNotNone(legs)
        self.assertEqual(legs[-1].after, {WorldState(goal)}, text(legs))
        self.assertTrue(all(len(leg.after) <= BeliefCosts().max_spread for leg in legs))

    def test_after_training_to_the_pokemon_center(self):
        #   Anywhere in the 3 x 3 around the catch spot, to below the Center's
        #   sign in Sandgem Town: across the map edge.
        start = [WorldState(Place("Route 202", Tile(x, y))) for x in (18, 19, 20) for y in (20, 21, 22)]
        goal = Place("Sandgem Town", Tile(20, 7))
        legs = plan_belief(self.world, start, goal)
        self.assertIsNotNone(legs)
        self.assertEqual(legs[-1].after, {WorldState(goal)}, text(legs))


POKEFIRERED = os.environ.get("POKEFIRERED_DIR", "")


@unittest.skipUnless(POKEFIRERED and os.path.isdir(POKEFIRERED), "set POKEFIRERED_DIR to a pokefirered checkout")
class Route1LedgeTest(unittest.TestCase):
    def test_each_drop_ends_on_one_row(self):
        from pokenav.maps.pret import Checkout
        world = Checkout(POKEFIRERED, frlg.PRET).load_world(["Route1"])
        planner = BeliefPlanner(world, rules=frlg.ELEVATION_RULES)
        #   Anywhere on rows 2 to 4 of the west side: each drop south pins the
        #   landing row, column by column.
        belief = frozenset(WorldState(Place("Route1", Tile(x, y)), 3) for x in (5, 6) for y in (3, 4))
        rows = []
        for _ in range(4):
            leg, _ = planner.ledge_leg(belief, S)
            landing_rows = {state.place.tile.y for state in leg.after}
            self.assertEqual(len(landing_rows), 1, describe(leg))
            rows.append(landing_rows.pop())
            belief = leg.after
        self.assertEqual(rows, [6, 11, 16, 21])


if __name__ == "__main__":
    unittest.main()
