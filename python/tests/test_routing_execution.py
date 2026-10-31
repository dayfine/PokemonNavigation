"""Tests for leg execution (pokenav.grid.routing.execution) in the robust
planner and scoring: on BDSP, counted D-pad taps beat stick holds, an
uncertain start is clipped to a wall before planning, and the bike is ridden
on long clips when the player has one."""

import unittest

from pokenav.games import bdsp
from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.schema import MapFile, Warp
from pokenav.grid.maps.textgrid import parse
from pokenav.grid.maps.world import Place, World
from pokenav.grid.movement import WorldState
from pokenav.grid.routing.belief import BeliefPlanner, describe
from pokenav.grid.routing.execution import Execution, bot_legs
from pokenav.grid.routing.localize import anchor, synchronize
from pokenav.grid.routing.score import checks, rank, score
from pokenav.physics.model import Mode

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST

#   A hand-made Oreburgh City street; BDSP's Oreburgh is not mapped yet
#   (games/bdsp/maps/ has Route 201 to Jubilife City). The shape follows the
#   2026-10-31 console runs (games/bdsp/MEASUREMENTS.md results #2 and #4):
#   leaving the Center lands on its doorstep, and D-pad taps west along the
#   row end below the Gym's door. The run took 22 taps, turn taps included;
#   here the doors are 20 tiles apart. The street's west end is a wall (the
#   cliff), so a stick walk west clips there.
CITY = "Oreburgh City"
CENTER = "Oreburgh Pokemon Center"
GYM_DOOR = Tile(2, 1)
CENTER_DOOR = Tile(22, 1)
STREET = parse("""\
#########################
##D###################D##
#.......................#
#########################
""", name=CITY).grid
#   The Center's floor, with its exit mat at (2, 3).
CENTER_FLOOR = parse("""\
#####
#...#
#...#
##W##
""", name=CENTER).grid


def oreburgh() -> World:
    """The street and the Center, joined by the Center's door. The Gym is not
    loaded, so its door is the end of a route."""
    street = MapFile(STREET, warps=[Warp(CENTER_DOOR, CENTER, 0), Warp(GYM_DOOR, "Oreburgh Gym", 0)])
    center = MapFile(CENTER_FLOOR, warps=[Warp(Tile(2, 3), CITY, 0)])
    return World([street, center])


def at(x, y, name=CITY):
    return WorldState(Place(name, Tile(x, y)))


DOORSTEP = at(22, 2)
BELOW_GYM_DOOR = at(2, 2)
IN_GYM_DOOR = Place(CITY, GYM_DOOR)


def text(legs):
    return "\n" + "\n".join(describe(leg) for leg in legs) if legs else " none"


def walk(planner, start, steps):
    """Planned legs from (execution, direction[, tiles]) steps."""
    belief, out = frozenset(start), []
    for step in steps:
        kind, direction = step[0], step[1]
        if kind is Execution.CLIP:
            found = planner.wall_leg(belief, direction)
        elif kind is Execution.DOOR:
            found = planner.door_leg(belief, direction)
        else:
            found = planner.open_leg(belief, direction, step[2], kind=kind)
        if found is None:
            return out
        out.append(found[0])
        belief = found[0].after
    return out


class OreburghTest(unittest.TestCase):
    def setUp(self):
        self.planner = BeliefPlanner(oreburgh(), bdsp.belief_costs())

    def test_exit_then_dpad_west_20_then_door(self):
        legs = self.planner.plan(at(2, 2, CENTER), IN_GYM_DOOR, facing=N)
        self.assertEqual(bot_legs(legs), [("door", "S"), ("dpad", "W", 20), ("door", "N")], text(legs))
        self.assertEqual(legs[0].after, {DOORSTEP})
        self.assertEqual([c.proof for c in checks([at(2, 2, CENTER)], legs)], ["door fade", "tap count", "door fade"])

    def test_stick_hold_alternative_scores_worse(self):
        dpad = walk(self.planner, [DOORSTEP], [(Execution.DPAD, W, 20), (Execution.DOOR, N)])
        stick = walk(self.planner, [DOORSTEP], [(Execution.STICK_HOLD, W, 20), (Execution.DOOR, N)])
        #   20 tiles of stick may end a tile either side of the door, so the
        #   door leg is refused: the stick route does not reach the Gym.
        self.assertEqual(stick[0].after, {at(1, 2), at(2, 2), at(3, 2)})
        self.assertEqual(len(stick), 1)
        ranked = rank(self.planner, [DOORSTEP], {"dpad": dpad, "stick": stick}, IN_GYM_DOOR)
        self.assertEqual([r.name for r in ranked], ["dpad"])
        self.assertEqual(ranked[0].score.risk, 0)

    def test_uncertain_start_is_clipped_to_the_wall_before_planning(self):
        #   Three tiles of doubt about where the player stands on the street:
        #   the planner wants one tile, so the bot clips to the street's end
        #   (routing.localize finds the leg) and plans from there.
        start = [at(21, 2), DOORSTEP, at(23, 2)]
        with self.assertRaises(TypeError):
            self.planner.plan(start, IN_GYM_DOOR)
        clip = synchronize(self.planner, start)
        self.assertEqual([leg.execution for leg, _ in clip], [Execution.CLIP])
        legs = self.planner.plan(anchor(clip), IN_GYM_DOOR, facing=clip[-1][0].direction)
        self.assertEqual([leg.execution for leg in legs], [Execution.DPAD, Execution.DOOR], text(legs))
        #   Counting taps from the uncertain start would miss the door.
        pure_count = walk(self.planner, start, [(Execution.DPAD, W, 20), (Execution.DOOR, N)])
        self.assertIsNone(score(self.planner, start, pure_count, IN_GYM_DOOR))

    def test_known_start_counts_instead_of_clipping(self):
        legs = self.planner.plan(DOORSTEP, IN_GYM_DOOR, facing=S)
        self.assertEqual(bot_legs(legs), [("dpad", "W", 20), ("door", "N")], text(legs))


#   A long corridor: walls at x = 0 and x = 49.
CORRIDOR = World([parse("""\
##################################################
#................................................#
##################################################
""", name="Corridor")])


class BikeTest(unittest.TestCase):
    def setUp(self):
        self.planner = BeliefPlanner(CORRIDOR, bdsp.belief_costs())
        self.start = at(1, 1, "Corridor")
        #   Three tiles short of the east wall: a clip, then an exact offset.
        self.goal = Place("Corridor", Tile(45, 1))

    def test_bike_rides_the_long_clip_and_offsets_on_foot(self):
        legs = self.planner.plan(self.start, self.goal, bike=True)
        self.assertEqual(bot_legs(legs), [("mount",), ("clip", "E"), ("dismount",), ("dpad", "W", 3)], text(legs))
        self.assertEqual([leg.mode for leg in legs], [Mode.BIKE, Mode.FOOT])

    def test_without_the_bike_it_walks(self):
        legs = self.planner.plan(self.start, self.goal)
        #   Counted on foot: two runs of taps, as a run is at most
        #   bdsp.MAX_COUNTED_TILES taps.
        self.assertTrue(all(leg.mode is Mode.FOOT and leg.execution is Execution.DPAD for leg in legs), text(legs))
        self.assertEqual(sum(leg.tiles for leg in legs), 44)


if __name__ == "__main__":
    unittest.main()
