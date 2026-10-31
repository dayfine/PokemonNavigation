"""Tests for pokenav.movement: one rule per case, on small text maps."""

import doctest
import unittest

from pokenav import movement
from pokenav.games import frlg
from pokenav.geometry import Direction, Tile
from pokenav.maps.textgrid import parse
from pokenav.movement import (
    FLAT, Blocked, BlockReason, Edge, Hop, Moved, PlayerState, Warp, held_at, step, walk,
)

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST


def load_tests(loader, tests, ignore):
    """Also runs the examples in the module's comments."""
    tests.addTests(doctest.DocTestSuite(movement))
    return tests


def grid_of(text):
    return parse(text).grid


def at(x, y, elevation=0):
    return PlayerState(Tile(x, y), elevation)


#   Row 2 is a ledge with a gap at x = 4; (1, 4) a sign, (5, 4) a door, (3, 0)
#   unknown ground, (2, 1) and (3, 1) tall grass.
SMALL = grid_of("""\
#..?..#
#..,,.#
#vvv..#
#.....#
#S...D#
""")

#   A bridge: the row-1 road at elevation 4 crosses a north-south path at
#   elevation 1 on a multi-level tile (F).
BRIDGE = grid_of("""\
##.##
.....
##.##
// Elevation:
// 33133
// 44F44
// 33133
""")

#   Levels 3 and 4 joined by a transition tile at elevation 0.
STAIRS = grid_of("""\
...
// Elevation:
// 304
""")


class StepTest(unittest.TestCase):
    def check(self, grid, cases, rules=FLAT, objects=frozenset()):
        for state, direction, expected in cases:
            with self.subTest(state=state, direction=direction):
                self.assertEqual(step(grid, state, direction, rules, objects), expected)

    def test_walls_and_open_ground(self):
        self.check(SMALL, [
            (at(1, 1), E, Moved(at(2, 1))),       # into tall grass
            (at(1, 1), W, Blocked(BlockReason.WALL)),
            (at(2, 3), S, Moved(at(2, 4))),
            (at(2, 4), W, Blocked(BlockReason.WALL)),   # the sign blocks
        ])

    def test_ledges_are_one_way_and_hop_two_tiles(self):
        self.check(SMALL, [
            (at(1, 1), S, Hop(at(1, 3))),
            (at(1, 3), N, Blocked(BlockReason.LEDGE)),
            (at(4, 3), N, Moved(at(4, 2))),       # the gap
        ])

    def test_a_ledge_with_no_landing_blocks(self):
        grid = grid_of(".\nv\n#\n")
        self.check(grid, [(at(0, 0), S, Blocked(BlockReason.LEDGE))])
        self.check(grid_of(".\nv\n.\n"), [(at(0, 0), S, Blocked(BlockReason.LEDGE))],
                   objects={Tile(0, 2)})

    def test_doors_warps_edges_and_unknown(self):
        self.check(SMALL, [
            (at(4, 4), E, Warp(Tile(5, 4))),
            (at(1, 0), N, Edge(N)),
            (at(2, 0), E, Blocked(BlockReason.UNKNOWN)),
        ])
        self.check(grid_of(".W\n"), [(at(0, 0), E, Warp(Tile(1, 0)))])

    def test_objects_block(self):
        self.check(SMALL, [(at(2, 3), E, Blocked(BlockReason.OBJECT))], objects={Tile(3, 3)})

    def test_water_blocks(self):
        self.check(grid_of(".~\n"), [(at(0, 0), E, Blocked(BlockReason.WALL))])

    def test_ice_slides_until_stopped(self):
        grid = grid_of(".iii#\n")
        self.check(grid, [(at(0, 0), E, Moved(at(3, 0)))])

    def test_forced_tiles_push_and_chain(self):
        grid = grid_of("""\
.662
...2
...#
""")
        #   East onto a push east, then onto a push south, which stops at (3, 1)
        #   because (3, 2) is a wall.
        self.check(grid, [(at(0, 0), E, Moved(at(3, 1)))])

    def test_a_loop_of_forced_tiles_ends(self):
        grid = grid_of("62\n84\n")
        result = step(grid, at(0, 0), E)
        self.assertIsInstance(result, Moved)

    def test_elevation_without_rules_must_match(self):
        self.check(STAIRS, [(at(0, 0, 3), E, Blocked(BlockReason.ELEVATION))])

    def test_transition_tiles_join_levels(self):
        rules = frlg.ELEVATION_RULES
        self.check(STAIRS, [
            (at(0, 0, 3), E, Moved(at(1, 0, 0))),
            (at(1, 0, 0), E, Moved(at(2, 0, 4))),
        ], rules)

    def test_bridge_keeps_the_level(self):
        rules = frlg.ELEVATION_RULES
        self.check(BRIDGE, [
            (at(1, 1, 4), E, Moved(at(2, 1, 4))),     # onto the bridge, still on top
            (at(2, 1, 4), E, Moved(at(3, 1, 4))),
            (at(2, 1, 4), S, Blocked(BlockReason.ELEVATION)),
            (at(2, 0, 1), S, Moved(at(2, 1, 1))),     # under the bridge
            (at(2, 1, 1), S, Moved(at(2, 2, 1))),
            (at(2, 1, 1), E, Blocked(BlockReason.ELEVATION)),
        ], rules)


class HeldAtTest(unittest.TestCase):
    def test_what_holds_the_player(self):
        cases = [
            (at(1, 1), W, True, frozenset()),           # a wall
            (at(1, 3), N, True, frozenset()),           # a ledge from below
            (at(2, 4), W, True, frozenset()),           # a sign
            (at(4, 4), E, False, frozenset()),          # a door
            (at(1, 0), N, False, frozenset()),          # the map edge
            (at(2, 0), E, False, frozenset()),          # unknown ground
            (at(2, 3), E, False, frozenset({Tile(3, 3)})),   # an NPC
            (at(1, 1), E, False, frozenset()),          # open ground
        ]
        for state, direction, held, objects in cases:
            with self.subTest(state=state, direction=direction):
                self.assertEqual(held_at(SMALL, state, direction, objects=objects), held)

    def test_elevation_holds(self):
        self.assertTrue(held_at(BRIDGE, at(2, 1, 4), S, frlg.ELEVATION_RULES))


class WalkTest(unittest.TestCase):
    def test_walks_until_stopped(self):
        cases = [
            (at(1, 1), E, at(5, 1), 4, True),     # through grass to the east wall
            (at(1, 0), S, at(1, 3), 3, True),     # hops the ledge, stops at the sign
            (at(2, 3), N, at(2, 3), 0, True),     # a ledge stops a north walk
            (at(4, 4), N, at(4, 0), 4, False),    # through the gap, off the top edge
            (at(4, 4), E, at(4, 4), 0, False),    # into the door
        ]
        for start, direction, end, tiles, held in cases:
            with self.subTest(start=start, direction=direction):
                result = walk(SMALL, start, direction)
                self.assertEqual((result.state, result.tiles, result.held), (end, tiles, held))

    def test_max_tiles(self):
        result = walk(SMALL, at(1, 1), E, max_tiles=2)
        self.assertEqual((result.state, result.tiles, result.stop), (at(3, 1), 2, None))
        hop = walk(SMALL, at(1, 1), S, max_tiles=1)
        self.assertEqual((hop.state, hop.tiles), (at(1, 3), 2))


if __name__ == "__main__":
    unittest.main()
