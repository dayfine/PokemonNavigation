"""Tests for pokenav.maps.textgrid: the legend table and the text format."""

import contextlib
import io
import os
import tempfile
import unittest

from pokenav.geometry import Direction, Tile
from pokenav.maps import schema, textgrid
from pokenav.maps.model import OPEN, WALL, Behavior, Cell, GridMap2D
from pokenav.maps.textgrid import STANDARD, Legend

from tests.paths import DOCS_EXAMPLES

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
        map_file = textgrid.read("#n#\n#N#\n", facing)
        self.assertEqual([npc.facing for npc in map_file.npcs], [Direction.NORTH, None])
        self.assertEqual(textgrid.write(map_file, facing).splitlines()[1:], ["#n#  // 0", "#N#  // 1"])


class ReadTest(unittest.TestCase):
    def test_cells_points_and_npcs(self):
        small = textgrid.read(SMALL)
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
        self.assertEqual(textgrid.read("..\n", name="given").name, "given")

    def test_elevation_layer(self):
        grid = textgrid.read("#.\n..\n// Elevation:\n// 3F\n// 0 1\n").grid
        self.assertEqual([[c.elevation for c in row] for row in grid.rows()], [[3, 15], [0, 1]])

    def test_malformed_text(self):
        bad = {
            "unknown character": "..x\n",
            "ragged rows": "...\n..\n",
            "elevation size": "..\n// Elevation:\n// 000\n",
        }
        for name, text in bad.items():
            with self.assertRaises(ValueError, msg=name):
                textgrid.read(text)


class WriteTest(unittest.TestCase):
    def test_round_trip(self):
        small = textgrid.read(SMALL)
        text = textgrid.write(small)
        self.assertEqual(textgrid.read(text), small)
        self.assertEqual(text.splitlines()[:3], ["// Map: Small", "//   START 1 0", "#..?..#  // 0"])

    def test_round_trip_with_elevation(self):
        text = "// Map: Hill\n#.  // 0\n..  // 1\n// Elevation:\n// 34\n// 00\n"
        self.assertEqual(textgrid.write(textgrid.read(text)), text)

    def test_cell_without_a_character(self):
        grid = GridMap2D("odd", [[Cell(behavior=Behavior.DOOR)]])
        with self.assertRaises(KeyError):
            textgrid.write(schema.MapFile(grid))

    def test_show_with_marks(self):
        small = textgrid.read(SMALL)
        shown = textgrid.show(small.grid, marks={Tile(1, 1): "@", Tile(9, 9): "x"})
        self.assertEqual(shown.splitlines()[1], '#@."".#')


class CommandLineTest(unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(textgrid.main(list(argv)), 0)
        return out.getvalue()

    def test_show_the_example(self):
        out = self.run_main("show", os.path.join(DOCS_EXAMPLES, "tiny_town.json"))
        self.assertIn("#N#  // 1", out)

    def test_convert_text_to_json_and_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            text_path = os.path.join(tmp, "small.txt")
            json_path = os.path.join(tmp, "small.json")
            back_path = os.path.join(tmp, "back.txt")
            with open(text_path, "w") as f:
                f.write(SMALL)
            self.run_main("convert", text_path, json_path)
            self.run_main("convert", json_path, back_path)
            self.assertEqual(schema.load(json_path), textgrid.read(SMALL))
            with open(back_path) as f:
                self.assertEqual(textgrid.read(f.read()), textgrid.read(SMALL))


if __name__ == "__main__":
    unittest.main()
