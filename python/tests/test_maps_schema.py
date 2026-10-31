"""Tests for pokenav.maps.schema: reading and writing JSON map files."""

import json
import os
import tempfile
import unittest

from pokenav.geometry import Direction, Tile
from pokenav.maps import schema
from pokenav.maps.model import OPEN, WALL, Behavior, Cell, MapGrid
from pokenav.maps.schema import MapFile, Npc, Wander

from tests.paths import DOCS_EXAMPLES

TINY_TOWN = os.path.join(DOCS_EXAMPLES, "tiny_town.json")

#   The legend tiny_town.json uses.
DOOR = Cell(blocked=True, behavior=Behavior.DOOR)
LEGEND = {"#": WALL, ".": OPEN, "D": DOOR}


def minimal(rows, legend=None, **extra):
    """The parsed form of a map file with only the required keys."""
    data = {
        "format": schema.FORMAT,
        "name": "test",
        "legend": legend or {"#": {"blocked": True}, ".": {}},
        "rows": rows,
    }
    data.update(extra)
    return data


class LoadTest(unittest.TestCase):
    def test_the_documented_example(self):
        town = schema.load(TINY_TOWN)
        self.assertEqual((town.name, town.game), ("Tiny Town", "example"))
        self.assertEqual((town.grid.width, town.grid.height), (3, 2))
        self.assertEqual(town.grid.at(Tile(1, 0)), DOOR._replace(elevation=3))
        self.assertEqual(town.grid.at(Tile(1, 1)), Cell(elevation=3))
        self.assertEqual(town.point("DOORSTEP").tile, Tile(1, 1))
        self.assertEqual(town.npcs, [Npc("guard", Tile(1, 1), Direction.SOUTH, sight=3)])
        self.assertIs(town.signs[0].facing, Direction.NORTH)
        self.assertEqual(town.buildings[0].door, Tile(1, 0))
        self.assertEqual((town.warps[0].to_map, town.warps[0].to_warp), ("Tiny Mart", 0))
        self.assertEqual(town.connections[0].offset, -4)
        self.assertEqual(town.notes[0].source, "console")

    def test_only_the_cells_are_required(self):
        town = schema.from_json(minimal(["#.", ".#"]))
        self.assertEqual(town.grid.rows(), [[WALL, OPEN], [OPEN, WALL]])
        self.assertEqual((town.points, town.npcs, town.game), ([], [], ""))
        with self.assertRaises(KeyError):
            town.point("NOWHERE")

    def test_wanderers(self):
        data = minimal(["..."], npcs=[{"name": "kid", "tile": [1, 0],
                                       "wander": {"low": [0, 0], "high": [2, 0], "rate": 0.5}}])
        kid = schema.from_json(data).npcs[0]
        self.assertEqual(kid.wander, Wander(Tile(0, 0), Tile(2, 0), 0.5))
        self.assertIsNone(kid.facing)

    def test_errors(self):
        bad = {
            "wrong format": dict(minimal(["."]), format="other/1"),
            "unknown character": minimal([".x"]),
            "ragged rows": minimal(["..", "."]),
            "elevation row count": minimal([".."], elevation=["00", "00"]),
            "elevation row width": minimal([".."], elevation=["0"]),
            "elevation digit": minimal([".."], elevation=["0G"]),
            "unknown behavior": minimal(["."], legend={".": {"behavior": "lava"}}),
            "legend key": minimal(["."], legend={"..": {}}),
        }
        for name, data in bad.items():
            with self.assertRaises(ValueError, msg=name):
                schema.from_json(data)

    def test_load_names_the_file_in_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w") as f:
                json.dump(minimal([".x"]), f)
            with self.assertRaisesRegex(ValueError, "bad.json"):
                schema.load(path)


class DumpTest(unittest.TestCase):
    def test_round_trip_of_the_example(self):
        with open(TINY_TOWN) as f:
            original = json.load(f)
        town = schema.loads(json.dumps(original))
        self.assertEqual(schema.to_json(town, LEGEND), original)
        self.assertEqual(schema.loads(schema.dumps(town, LEGEND)), town)

    def test_writes_only_what_is_set(self):
        grid = MapGrid("plain", [[WALL, OPEN]])
        data = schema.to_json(MapFile(grid), LEGEND)
        self.assertEqual(data, {
            "format": schema.FORMAT,
            "name": "plain",
            "legend": {"#": {"blocked": True}, ".": {}},
            "rows": ["#."],
        })

    def test_cell_without_a_character(self):
        grid = MapGrid("pond", [[Cell(blocked=True, behavior=Behavior.WATER)]])
        with self.assertRaisesRegex(ValueError, "no legend character"):
            schema.dumps(MapFile(grid), LEGEND)

    def test_dump_and_load_a_file(self):
        town = schema.load(TINY_TOWN)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "town.json")
            schema.dump(path, town, LEGEND)
            self.assertEqual(schema.load(path), town)


if __name__ == "__main__":
    unittest.main()
