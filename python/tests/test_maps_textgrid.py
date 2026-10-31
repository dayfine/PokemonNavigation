"""Tests for pokenav.grid.maps.textgrid: the legend table and the text format."""

import unittest

from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps import schema, textgrid
from pokenav.grid.maps.model import OPEN, WALL, Behavior, Cell, GridMap2D
from pokenav.grid.maps.textgrid import STANDARD, Legend

#   A small map with most of the legend. Row 2 is a ledge with a gap at
#   x = 4; the bottom row has a sign, an NPC and a door; (3, 0) is unknown.
SMALL = """\
// Map: Small
// A free comment line.
//   START 1 0
#..?..#   // 0
#..\"\".#   // 1
#vvv..#
#.....#
#S.N.D#   // 4
"""


class LegendTest(unittest.TestCase):
    def test_standard_is_two_way(self):
        for char, cell in STANDARD.cells().items():
            self.assertEqual(STANDARD.char(cell), char)
            self.assertEqual(STANDARD.cell(char), cell)

    def test_standard_covers_every_behavior(self):
        behaviors = {cell.behavior for cell in STANDARD.cells().values()}
        self.assertEqual(behaviors, set(Behavior))

    def test_char_ignores_elevation(self):
        self.assertEqual(STANDARD.char(Cell(blocked=True, elevation=7)), "#")

    def test_rejects_entries_that_are_not_one_to_one(self):
        with self.assertRaises(ValueError):
            Legend([("#", WALL), ("X", WALL)])
        with self.assertRaises(ValueError):
            Legend([("#", WALL), ("#", OPEN)])
        with self.assertRaises(ValueError):
            Legend([("#", WALL)], npcs=[("#", None)])
        with self.assertRaises(ValueError):
            Legend([("##", WALL)])

    def test_show_char_falls_back_to_the_nearest_kind(self):
        self.assertEqual(STANDARD.show_char(Cell(blocked=False, behavior=Behavior.LEDGE_SOUTH)), "v")
        self.assertEqual(STANDARD.show_char(Cell(blocked=True, behavior=Behavior.TALL_GRASS)), '"')
        self.assertEqual(Legend([(".", OPEN)]).show_char(WALL), "?")

    def test_a_legend_with_npc_facings(self):
        facing = Legend(STANDARD.cells().items(), npcs=[("N", None), ("n", Direction.NORTH)])
        map_file = textgrid.parse("#n#\n#N#\n", facing)
        self.assertEqual([npc.facing for npc in map_file.npcs], [Direction.NORTH, None])
        self.assertEqual(textgrid.serialize(map_file, facing).splitlines()[1:], ["#n#  // 0", "#N#  // 1"])


class ReadTest(unittest.TestCase):
    def test_cells_points_and_npcs(self):
        small = textgrid.parse(SMALL)
        grid = small.grid
        self.assertEqual((grid.name, grid.width, grid.height), ("Small", 7, 5))
        expected = {
            Tile(0, 0): WALL,
            Tile(1, 0): OPEN,
            Tile(3, 0): Cell(blocked=True, behavior=Behavior.UNKNOWN),
            Tile(3, 1): Cell(behavior=Behavior.TALL_GRASS),
            Tile(2, 2): Cell(blocked=True, behavior=Behavior.LEDGE_SOUTH),
            Tile(1, 4): Cell(blocked=True, behavior=Behavior.SIGN),
            Tile(3, 4): OPEN,
            Tile(5, 4): Cell(blocked=True, behavior=Behavior.DOOR),
        }
        for tile, cell in expected.items():
            self.assertEqual(grid.at(tile), cell, tile)
        self.assertEqual(small.point("START").tile, Tile(1, 0))
        self.assertEqual([npc.tile for npc in small.npcs], [Tile(3, 4)])

    def test_name_from_the_caller_when_the_text_has_none(self):
        self.assertEqual(textgrid.parse("..\n", name="given").name, "given")

    def test_elevation_layer(self):
        grid = textgrid.parse("#.\n..\n// Elevation:\n// 3F\n// 0 1\n").grid
        self.assertEqual([[c.elevation for c in row] for row in grid.rows()], [[3, 15], [0, 1]])

    def test_malformed_text(self):
        bad = {
            "unknown character": "..x\n",
            "ragged rows": "...\n..\n",
            "elevation size": "..\n// Elevation:\n// 000\n",
        }
        for name, text in bad.items():
            with self.assertRaises(ValueError, msg=name):
                textgrid.parse(text)


class WriteTest(unittest.TestCase):
    def test_round_trip(self):
        small = textgrid.parse(SMALL)
        text = textgrid.serialize(small)
        self.assertEqual(textgrid.parse(text), small)
        self.assertEqual(textgrid.serialize(textgrid.parse(text)), text)
        self.assertEqual(text.splitlines()[:3], ["// Map: Small", "//   START 1 0", "#..?..#  // 0"])

    def test_round_trip_with_elevation(self):
        text = "// Map: Hill\n#.  // 0\n..  // 1\n// Elevation:\n// 34\n// 00\n"
        self.assertEqual(textgrid.serialize(textgrid.parse(text)), text)

    def test_cell_without_a_character(self):
        grid = GridMap2D("odd", [[Cell(behavior=Behavior.DOOR)]])
        with self.assertRaises(KeyError):
            textgrid.serialize(schema.MapFile(grid))

    def test_show_with_marks(self):
        small = textgrid.parse(SMALL)
        shown = textgrid.show(small.grid, marks={Tile(1, 1): "@", Tile(9, 9): "x"})
        self.assertEqual(shown.splitlines()[1], '#@."".#')


if __name__ == "__main__":
    unittest.main()
