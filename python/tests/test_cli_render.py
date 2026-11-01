"""Tests for pokenav.cli.render: drawing a route from the command line."""

import contextlib
import io
import os
import tempfile
import unittest

from pokenav.cli import render as cli
from pokenav.grid.geometry import Tile
from pokenav.grid.maps import render
from pokenav.png import Image

from tests.paths import REPO
from tests.test_maps_render import BACKGROUND


class ParseTileTest(unittest.TestCase):
    def test_x_comma_y(self):
        self.assertEqual(cli.parse_tile("19,22"), Tile(19, 22))


class CommandLineTest(unittest.TestCase):
    MAP = os.path.join(REPO, "games", "bdsp", "maps", "route_202.json")
    TOWN = os.path.join(REPO, "docs", "examples", "tiny_town.json")

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(list(argv)), 0)
        return out.getvalue()

    def test_text(self):
        out = self.run_main(self.MAP, "--path", "18,27", "29,27", "29,24", "--region", "28,24", "29,24")
        self.assertEqual(out.splitlines()[24], "##,,,,##.....########.......oX##")
        self.assertEqual(out.splitlines()[27], "##,,,,,,......,,,,@***********##")

    def test_picture_without_an_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "route.png")
            self.run_main(self.MAP, "--path", "18,27", "29,27", "--out", out_path)
            image = Image.read(out_path)
        self.assertEqual((image.width, image.height), (32 * 16, 32 * 16))

    def test_picture_over_an_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            picture = os.path.join(tmp, "map.png")
            Image(64, 32, BACKGROUND).write(picture)
            out_path = os.path.join(tmp, "route.png")
            self.run_main(self.TOWN, "--path", "0,1", "2,1", "--image", picture, "--out", out_path)
            image = Image.read(out_path)
        #   Tiny Town's picture puts tile (x, y) at pixel (8 + 16x, 16y).
        self.assertEqual(image.get(8 + 1 * 16 + 8, 1 * 16 + 8), render.LEG_COLORS[0])


if __name__ == "__main__":
    unittest.main()
