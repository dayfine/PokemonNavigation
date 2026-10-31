"""Tests for pokenav.grid.routing.belief: plans start from one known tile,
walls and ledges collapse beliefs, open legs spread them by the measured error
model and are allowed only into a goal wide enough or within `max_spread`,
doors and edges are avoided, and robust plans on BDSP's story maps and (with
POKEFIRERED_DIR) FRLG's Route 1."""

import os
import unittest

from pokenav.games import bdsp, frlg
from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.textgrid import parse
from pokenav.grid.maps.world import Place, World
from pokenav.grid.movement import WorldState
from pokenav.grid.routing.belief import (
    MAX_SPREAD, MEASURED_STICK, BeliefCosts, BeliefPlanner, LegEnd, describe, plan_belief,
)
from pokenav.physics.model import TileError

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST

ROOM = World([parse("""\
#######
#.....#
#.....#
#.....#
#.....#
#######
""", name="Room")])

#   A street 19 tiles long and 4 wide, closed at the west end and running off
#   the known map at the east, so nothing east of the start pins a column:
#   only an open leg reaches the middle. After Jubilife City's main street,
#   where a 14-tile stick hold from the first tile landed in the middle of a
#   4-wide stretch (BDSP runs, 2026-10-31).
STREET = World([parse("""\
####################?
#...................?
#...................?
#...................?
#...................?
####################?
""", name="Street")])

#   An error model coarser than the measured one: every hold may slide a tile.
COARSE = TileError(overshoot=1)


def at(x, y, name="Room", elevation=0):
    return WorldState(Place(name, Tile(x, y)), elevation)


def text(legs):
    return "\n" + "\n".join(describe(leg) for leg in legs) if legs else " none"


def between(x_min, x_max, y, name="Street"):
    """A goal region: the tiles from `x_min` to `x_max` on row `y`."""
    return lambda s: s.place.map == name and s.place.tile.y == y and x_min <= s.place.tile.x <= x_max


class TileErrorTest(unittest.TestCase):
    def test_measured_stick_is_exact_to_11_tiles(self):
        self.assertEqual([MEASURED_STICK.spread(n) for n in (1, 11, 12, 14, 99, 100)], [0, 0, 1, 1, 1, 2])

    def test_exact_and_overshoot(self):
        self.assertEqual(TileError().spread(30), 0)
        self.assertEqual(TileError(overshoot=1).spread(1), 1)


class StartTest(unittest.TestCase):
    def test_plans_start_from_one_known_tile(self):
        legs = plan_belief(ROOM, at(1, 1), Place("Room", Tile(1, 4)))
        self.assertEqual(legs[-1].after, {at(1, 4)}, text(legs))

    def test_a_set_of_start_tiles_is_refused(self):
        with self.assertRaises(TypeError):
            plan_belief(ROOM, [at(1, 1), at(2, 1)], Place("Room", Tile(1, 4)))
        with self.assertRaises(TypeError):
            BeliefPlanner(ROOM).plan([at(1, 1)], Place("Room", Tile(1, 4)))


class BeliefTest(unittest.TestCase):
    def test_walls_collapse_a_row(self):
        planner = BeliefPlanner(ROOM)
        row = frozenset(at(x, 1) for x in range(1, 6))
        leg, _ = planner.wall_leg(row, S)
        self.assertEqual(leg.after, frozenset(at(x, 4) for x in range(1, 6)))
        leg, _ = planner.wall_leg(leg.after, W)
        self.assertEqual(leg.after, {at(1, 4)})
        self.assertIs(leg.end, LegEnd.WALL)

    def test_short_holds_are_exact(self):
        #   The middle of the room is reached only by open legs; with the
        #   measured error, holds this short land exactly.
        legs = plan_belief(ROOM, at(1, 1), Place("Room", Tile(3, 2)))
        self.assertEqual(legs[-1].after, {at(3, 2)}, text(legs))
        self.assertTrue(all(len(leg.after) == 1 for leg in legs), text(legs))
        #   Were every hold to miss a tile, no plan would pin the column.
        self.assertIsNone(plan_belief(ROOM, at(1, 1), Place("Room", Tile(3, 2)), BeliefCosts(error=COARSE)))

    def test_open_leg_reports_its_spread(self):
        planner = BeliefPlanner(ROOM, BeliefCosts(error=COARSE))
        legs = {leg.tiles: leg for leg, _ in planner.open_legs(frozenset({at(1, 2)}), E)}
        self.assertEqual(legs[2].after, {at(2, 2), at(3, 2), at(4, 2)})
        #   Near the wall the spread is cut short by it.
        self.assertEqual(legs[4].after, {at(4, 2), at(5, 2)})

    def test_goal_region(self):
        legs = plan_belief(ROOM, at(1, 2), lambda s: s.place.tile.y == 4 and 2 <= s.place.tile.x <= 4)
        self.assertIsNotNone(legs)
        for state in legs[-1].after:
            self.assertTrue(state.place.tile.y == 4 and 2 <= state.place.tile.x <= 4, text(legs))

    def test_avoids_doors(self):
        #   North from (2, 3) would walk into the door; the plan goes round.
        world = World([parse("##D###\n#....#\n#....#\n#....#\n######\n", name="Room")])
        legs = plan_belief(world, at(2, 3), Place("Room", Tile(1, 1)))
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
        #   Only the one tile before it can be held for.
        self.assertEqual([l.tiles for l, _ in planner.open_legs(frozenset({at(2, 0, "Field")}), S)], [1])
        self.assertIsNone(planner.ledge_leg(frozenset({at(2, 3, "Field")}), S))


class OpenLegIntoGoalTest(unittest.TestCase):
    """A long stick hold is allowed where its spread is absorbed by the goal
    region, and refused into a narrower one or past `max_spread`."""

    START = at(1, 2, "Street")
    #   Long enough for one hold down the street.
    COSTS = BeliefCosts(max_open_tiles=20)

    def test_a_14_tile_hold_into_a_4_wide_goal(self):
        legs = plan_belief(STREET, self.START, between(14, 17, 2), self.COSTS)
        self.assertEqual([describe(leg) for leg in legs],
                         ["stick east (14 tiles) -> Street (14, 2), Street (15, 2), Street (16, 2)"])
        self.assertEqual(len(legs[0].after), 1 + 2 * MEASURED_STICK.spread(14))

    def test_into_a_2_wide_goal_the_hold_is_refused(self):
        planner = BeliefPlanner(STREET, self.COSTS)
        narrow = between(15, 16, 2)
        hold = {leg.tiles: leg for leg, _ in planner.open_legs(frozenset({self.START}), E)}[14]
        self.assertFalse(all(narrow(state) for state in hold.after), describe(hold))
        #   The plan found instead keeps every hold short enough to be exact.
        legs = planner.plan(self.START, narrow)
        self.assertTrue(all(len(leg.after) == 1 for leg in legs), text(legs))
        self.assertEqual(sum(leg.tiles for leg in legs), 14, text(legs))

    def test_a_spread_above_max_spread_is_refused(self):
        coarse = self.COSTS._replace(error=COARSE)
        legs = plan_belief(STREET, self.START, between(14, 17, 2), coarse)
        self.assertEqual(len(legs[-1].after), 3, text(legs))
        self.assertEqual(coarse.max_spread, MAX_SPREAD)
        self.assertIsNone(plan_belief(STREET, self.START, between(14, 17, 2), coarse._replace(max_spread=2)))


class StoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = bdsp.story_world()

    def test_route202_catch_spot_to_save_spot(self):
        start = WorldState(Place("Route 202", Tile(19, 22)))
        goal = Place("Route 202", Tile(30, 19))
        legs = plan_belief(self.world, start, goal)
        self.assertIsNotNone(legs)
        self.assertEqual(legs[-1].after, {WorldState(goal)}, text(legs))
        self.assertTrue(all(len(leg.after) <= BeliefCosts().max_spread for leg in legs))

    def test_after_training_to_the_pokemon_center(self):
        #   From the catch spot to below the Center's sign in Sandgem Town:
        #   across the map edge.
        start = WorldState(Place("Route 202", Tile(19, 22)))
        goal = Place("Sandgem Town", Tile(20, 7))
        legs = plan_belief(self.world, start, goal)
        self.assertIsNotNone(legs)
        self.assertEqual(legs[-1].after, {WorldState(goal)}, text(legs))


POKEFIRERED = os.environ.get("POKEFIRERED_DIR", "")


@unittest.skipUnless(POKEFIRERED and os.path.isdir(POKEFIRERED), "set POKEFIRERED_DIR to a pokefirered checkout")
class Route1LedgeTest(unittest.TestCase):
    def test_each_drop_ends_on_one_row(self):
        from pokenav.grid.maps.pret import Checkout
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
