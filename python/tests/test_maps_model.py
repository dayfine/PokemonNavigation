"""Tests for pokenav.maps.model: cells, behaviors, a map's bounds and the
viewport."""

import doctest
import unittest

from pokenav.geometry import Direction, Tile
from pokenav.maps import model
from pokenav.maps.model import (
    FORCED_DIRECTION, LEDGE_DIRECTION, OPEN, WALL, Behavior, Cell, GridMap2D, Viewport,
)


def load_tests(loader, tests, ignore):
    """Also runs the examples in the module's comments."""
    tests.addTests(doctest.DocTestSuite(model))
    return tests


#   A viewport the size of the GBA screen: 15 x 10 tiles, player at (7, 4).
SCREEN = Viewport(width=15, height=10, player_x=7, player_y=4)


def every_behavior_map() -> GridMap2D:
    """A one-row map with one cell of each behavior, in enum order."""
    row = [Cell(blocked=(b is not Behavior.NONE), behavior=b) for b in Behavior]
    return GridMap2D("behaviors", [row])


class CellTest(unittest.TestCase):
    def test_defaults_are_open_ground(self):
        self.assertEqual(Cell(), OPEN)
        self.assertEqual((OPEN.blocked, OPEN.elevation, OPEN.behavior), (False, 0, Behavior.NONE))
        self.assertTrue(WALL.blocked)

    def test_behavior_values_are_file_names(self):
        self.assertIs(Behavior("ledge_south"), Behavior.LEDGE_SOUTH)
        self.assertEqual(len({b.value for b in Behavior}), len(Behavior))

    def test_ledge_and_forced_tables_cover_each_direction_once(self):
        self.assertEqual(set(LEDGE_DIRECTION.values()), set(Direction))
        self.assertEqual(set(FORCED_DIRECTION.values()), set(Direction))
        self.assertIs(LEDGE_DIRECTION[Behavior.LEDGE_WEST], Direction.WEST)
        self.assertNotIn(Behavior.DOOR, LEDGE_DIRECTION)


class GridMap2DTest(unittest.TestCase):
    def test_construction(self):
        grid = GridMap2D.filled("field", 4, 3)
        self.assertEqual((grid.name, grid.width, grid.height), ("field", 4, 3))
        self.assertEqual(len(list(grid.tiles())), 12)
        self.assertEqual(grid.rows(), [[OPEN] * 4] * 3)
        self.assertEqual(grid, GridMap2D.filled("field", 4, 3))
        self.assertNotEqual(grid, GridMap2D.filled("field", 3, 4))

    def test_rejects_ragged_rows_and_bad_elevations(self):
        with self.assertRaises(ValueError):
            GridMap2D("ragged", [[OPEN, OPEN], [OPEN]])
        with self.assertRaises(ValueError):
            GridMap2D("high", [[Cell(elevation=16)]])
        with self.assertRaises(ValueError):
            GridMap2D("low", [[Cell(elevation=-1)]])

    def test_bounds_report_the_edge_crossed(self):
        grid = GridMap2D.filled("field", 4, 3)
        cases = {
            Tile(0, 0): None,
            Tile(3, 2): None,
            Tile(1, -1): Direction.NORTH,
            Tile(1, 3): Direction.SOUTH,
            Tile(-1, 1): Direction.WEST,
            Tile(4, 1): Direction.EAST,
            Tile(-1, -1): Direction.NORTH,
        }
        for tile, edge in cases.items():
            self.assertIs(grid.edge_crossed(tile), edge, tile)
            self.assertEqual(grid.contains(tile), edge is None, tile)
            self.assertEqual(grid.at(tile) is None, edge is not None, tile)

    def test_lookup_of_each_behavior(self):
        grid = every_behavior_map()
        for x, behavior in enumerate(Behavior):
            self.assertIs(grid.at(Tile(x, 0)).behavior, behavior)

    def test_set_replaces_one_cell(self):
        grid = GridMap2D.filled("field", 2, 2)
        grid.set(Tile(1, 0), WALL)
        self.assertEqual(grid.at(Tile(1, 0)), WALL)
        self.assertEqual(grid.at(Tile(0, 0)), OPEN)
        with self.assertRaises(IndexError):
            grid.set(Tile(2, 0), WALL)


class ViewportTest(unittest.TestCase):
    def test_window_is_centered_on_the_player(self):
        window = list(SCREEN.window(Tile(10, 10)))
        self.assertEqual(len(window), 150)
        self.assertEqual(window[0], Tile(3, 6))
        self.assertEqual(window[-1], Tile(17, 15))


if __name__ == "__main__":
    unittest.main()
