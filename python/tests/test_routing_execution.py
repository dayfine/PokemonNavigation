"""Tests for leg execution (pokenav.grid.routing.execution) in the robust
planner and scoring: on BDSP, counted D-pad taps beat stick holds, a run to a
wall beats both where the player can run, an uncertain start is clipped to a
wall before planning, stick legs are refused where they could drift into a
corner, and the bike is ridden on long clips when the player has one."""

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


def no_run_costs():
    """BDSP's costs without running, as before the Running Shoes."""
    costs = bdsp.belief_costs()
    model = costs.execution
    return costs._replace(execution=model._replace(foot=model.foot._replace(run=None)))


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
        #   Without running, as the 2026-10-31 runs were walked.
        self.planner = BeliefPlanner(oreburgh(), no_run_costs())
        self.running = BeliefPlanner(oreburgh(), bdsp.belief_costs())

    def test_exit_then_dpad_west_20_then_door(self):
        legs = self.planner.plan(at(2, 2, CENTER), IN_GYM_DOOR, facing=N)
        self.assertEqual(bot_legs(legs), [("door", "S"), ("dpad", "W", 20), ("door", "N")], text(legs))
        self.assertEqual(legs[0].after, {DOORSTEP})
        self.assertEqual([c.proof for c in checks([at(2, 2, CENTER)], legs)], ["door fade", "tap count", "door fade"])

    def test_with_running_it_runs_to_the_cliff_and_taps_back(self):
        #   Running is guessed at twice walking's speed: a run to the street's
        #   west end and one tap back cost less than 20 taps.
        legs = self.running.plan(at(2, 2, CENTER), IN_GYM_DOOR, facing=N)
        self.assertEqual(bot_legs(legs), [("door", "S"), ("run", "W"), ("dpad", "E", 1), ("door", "N")], text(legs))
        self.assertEqual([c.proof for c in checks([at(2, 2, CENTER)], legs)],
                         ["door fade", "wall bump", "tap count", "door fade"])
        self.assertEqual(score(self.running, [at(2, 2, CENTER)], legs, IN_GYM_DOOR).risk, 0)

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


class DriftTest(unittest.TestCase):
    """A stick hold drifts sideways (BDSP, Route 203), so it is allowed only
    where what lies beside it is all wall or all open along the leg."""

    def tiles(self, text, kind, start=(1, 2)):
        """The lengths of the legs of `kind` east from `start` on map `text`:
        0 for a clip that is allowed (its length is not counted)."""
        planner = BeliefPlanner(World([parse(text, name="M")]), bdsp.belief_costs())
        belief = frozenset({at(start[0], start[1], "M")})
        if kind is Execution.CLIP:
            return [] if planner.wall_leg(belief, E) is None else [0]
        return [leg.tiles for leg, _ in planner.open_legs(belief, E, kind)]

    #   The row is 8 tiles long; holds longer than that end at its east wall.
    EIGHT = list(range(1, 9))

    def test_a_straight_corridor_may_be_held_along(self):
        corridor = "##########\n##########\n#........#\n##########\n"
        self.assertEqual(self.tiles(corridor, Execution.STICK_HOLD)[:8], self.EIGHT)
        self.assertEqual(self.tiles(corridor, Execution.CLIP), [0])

    def test_a_ragged_tree_line_takes_the_dpad(self):
        #   Trees above the row with gaps: a hold east catches their corners.
        ragged = "##########\n#..##..###\n#........#\n##########\n"
        #   Only the one-tile hold stays beside open ground the whole way.
        self.assertEqual(self.tiles(ragged, Execution.STICK_HOLD), [1])
        self.assertEqual(self.tiles(ragged, Execution.CLIP), [])
        self.assertEqual(self.tiles(ragged, Execution.DPAD)[:8], self.EIGHT)

    def test_a_ledge_beside_the_row_is_a_hazard(self):
        #   Ledges below the row, crossed south: a drift would hop them. (A
        #   ledge above, met from below, is a wall.)
        ledges = "##########\n##########\n#........#\n#vvvvvvvv#\n#........#\n##########\n"
        self.assertEqual(self.tiles(ledges, Execution.STICK_HOLD), [])
        self.assertEqual(self.tiles(ledges, Execution.CLIP), [])
        self.assertEqual(self.tiles(ledges, Execution.DPAD)[:8], self.EIGHT)

    def test_a_wide_street_may_be_held_along(self):
        #   Open ground on both sides the whole way, as on Jubilife's street.
        street = "##########\n#........#\n#........#\n#........#\n##########\n"
        self.assertEqual(self.tiles(street, Execution.STICK_HOLD)[:8], self.EIGHT)


#   A long corridor: walls at x = 0 and x = 49.
CORRIDOR = World([parse("""\
##################################################
#................................................#
##################################################
""", name="Corridor")])


class BikeTest(unittest.TestCase):
    def setUp(self):
        self.planner = BeliefPlanner(CORRIDOR, no_run_costs())
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

    def test_running_to_the_wall_beats_taps_and_the_guessed_bike(self):
        #   With the bike guessed no faster than running, mounting does not
        #   pay; the run ends at the wall, so its unmeasured speed is harmless.
        running = BeliefPlanner(CORRIDOR, bdsp.belief_costs())
        for bike in (False, True):
            legs = running.plan(self.start, self.goal, bike=bike)
            self.assertEqual(bot_legs(legs), [("run", "E"), ("dpad", "W", 3)], text(legs))


if __name__ == "__main__":
    unittest.main()
