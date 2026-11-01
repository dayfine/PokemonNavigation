"""Tests for pokenav.cli.decomp: writing map files from a checkout."""

import os
import tempfile
import unittest

from pokenav.cli import decomp
from pokenav.grid.maps import schema
from pokenav.grid.maps.model import Behavior

from tests.test_decomp_repos import write_platinum


class CommandLineTest(unittest.TestCase):
    def test_writes_the_map_and_reports_components(self):
        with tempfile.TemporaryDirectory() as root:
            write_platinum(root)
            out = os.path.join(root, "town.json")
            with self.assertLogs() if False else _silence() as output:
                decomp.main(["--repo", root, "--source", "pokeplatinum", "--game", "test", "--name", "Tiny Town",
                             "--cells", "0,0", "--events", "tiny_town", "--commit", "abc", "--out", out])
            self.assertEqual(output.text(), "wrote %s (32 x 32), 1 walkable component\n" % out)
            town = schema.load(out)
            self.assertEqual((town.name, town.game), ("Tiny Town", "test"))
            self.assertEqual(town.grid.at(town.warps[0].tile).behavior, Behavior.DOOR)
            self.assertEqual(town.grid.at(town.npcs[0].tile).behavior, Behavior.NONE)
            self.assertEqual(town.encounters, {schema.Encounter.GRASS, schema.Encounter.WATER})

    def test_crop_component_and_keep(self):
        with tempfile.TemporaryDirectory() as root:
            write_platinum(root)
            kept = os.path.join(root, "kept.json")
            with open(kept, "w") as f:
                f.write('{"format": "pokenav-map/1", "name": "k", "legend": {".": {}}, "rows": ["."], '
                        '"points": [{"name": "ROOM", "tile": [4, 4]}], "status": "walked once"}')
            out = os.path.join(root, "crop.json")
            with _silence() as output:
                decomp.main(["--repo", root, "--source", "pokeplatinum", "--name", "Room", "--cells", "0,0",
                             "--events", "tiny_town", "--crop", "8,8,40,12", "--component", "12,12",
                             "--keep", kept, "--out", out])
            self.assertIn("(40 x 12), 1 walkable component", output.text())
            room = schema.load(out)
            self.assertEqual(room.point("ROOM").tile.x, 4)
            self.assertEqual(room.status, "walked once")
            self.assertEqual(room.grid.at(room.point("ROOM").tile).behavior, Behavior.NONE)
            self.assertEqual(room.grid.at(schema.Tile(30, 2)).behavior, Behavior.UNKNOWN)   # Tiny Route, cut off

    def test_bad_numbers(self):
        with self.assertRaises(SystemExit):
            decomp.main(["--repo", "/nowhere", "--source", "pokeplatinum", "--name", "x", "--cells", "0", "--out", "o"])


class _silence:
    """Captures what main prints."""

    def __enter__(self):
        import io
        import sys
        self._stdout, self._buffer = sys.stdout, io.StringIO()
        sys.stdout = self._buffer
        return self

    def __exit__(self, *exc):
        import sys
        sys.stdout = self._stdout

    def text(self):
        return self._buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
