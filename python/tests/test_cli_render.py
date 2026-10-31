"""Tests for pokenav.cli.render: drawing a route from the command line."""

import contextlib
import io
import os
import tempfile
import unittest

from pokenav.cli import render as cli
from pokenav.geometry import Tile
from pokenav.maps import render
from pokenav.png import Image

from tests.paths import REPO
from tests.test_maps_render import BACKGROUND


class ParseTileTest(unittest.TestCase):
    def test_x_comma_y(self):
        self.assertEqual(cli.parse_tile("19,22"), Tile(19, 22))


class CommandLineTest(unittest.TestCase):
    MAP = os.path.join(REPO, "games", "bdsp", "maps", "route_202.json")

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(list(argv)), 0)
        return out.getvalue()

    def test_text(self):
        out = self.run_main(self.MAP, "--path", "19,22", "30,22", "30,19", "--region", "29,19", "30,19")
        self.assertEqual(out.splitlines()[19], "###,,,,##.....########.......oX#####")
        self.assertEqual(out.splitlines()[22], "###,,,,,,......,,,,@***********#####")

    def test_picture_without_an_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "route.png")
            self.run_main(self.MAP, "--path", "19,22", "30,22", "--out", out_path)
            image = Image.read(out_path)
        self.assertEqual((image.width, image.height), (36 * 16, 26 * 16))

    def test_picture_over_an_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            picture = os.path.join(tmp, "map.png")
            Image(592, 416, BACKGROUND).write(picture)
            out_path = os.path.join(tmp, "route.png")
            self.run_main(self.MAP, "--path", "19,22", "30,22", "--image", picture, "--out", out_path)
            image = Image.read(out_path)
        #   Route 202's picture puts tile (x, y) at pixel (8 + 16x, 16y).
        self.assertEqual(image.get(8 + 25 * 16 + 8, 22 * 16 + 8), render.LEG_COLORS[0])


if __name__ == "__main__":
    unittest.main()
