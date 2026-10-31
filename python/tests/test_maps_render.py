"""Tests for pokenav.maps.render: the text form (snapshots), drawing on a
picture lined up with the grid, and the command line."""

import contextlib
import io
import os
import tempfile
import unittest

from pokenav.geometry import Tile
from pokenav.maps import render
from pokenav.maps.render import Overlay
from pokenav.maps.schema import MapImage
from pokenav.maps.textgrid import parse
from pokenav.png import Image

from tests.paths import REPO

ROOM = parse("""\
######
#....#
#.,,.#
#....#
######
""").grid

#   A picture with an 8 px margin on the left and 4 px tiles.
CALIBRATION = MapImage("room.png", 8, 0, 4)
BACKGROUND = (0, 0, 0, 255)


class TextTest(unittest.TestCase):
    def test_route_and_region(self):
        overlay = Overlay(render.legs_through([Tile(1, 1), Tile(4, 1), Tile(4, 3)]),
                          [{Tile(1, 3), Tile(2, 3), Tile(4, 3)}])
        self.assertEqual(render.ascii(ROOM, overlay), """\
######
#@***#
#.,,*#
#oo.X#
######
""")

    def test_nothing_to_draw(self):
        self.assertEqual(render.ascii(ROOM, Overlay()).splitlines()[2], "#.,,.#")

    def test_legs_through_waypoints(self):
        self.assertEqual(render.legs_through([Tile(1, 1), Tile(1, 3), Tile(0, 3)]),
                         [[Tile(1, 1), Tile(1, 2), Tile(1, 3)], [Tile(1, 3), Tile(0, 3)]])
        with self.assertRaises(ValueError):
            render.legs_through([Tile(0, 0), Tile(1, 1)])


class PictureTest(unittest.TestCase):
    def picture(self):
        return Image(8 + 6 * 4, 5 * 4, BACKGROUND)

    def test_regions_are_tinted_on_their_tiles(self):
        image = render.draw(self.picture(), CALIBRATION, Overlay(regions=[{Tile(2, 2)}]))
        inside = image.get(8 + 2 * 4 + 1, 2 * 4 + 1)
        self.assertNotEqual(inside, BACKGROUND)
        self.assertEqual(image.get(8 + 3 * 4 + 1, 2 * 4 + 1), BACKGROUND)

    def test_legs_run_between_tile_centers(self):
        overlay = Overlay(render.legs_through([Tile(1, 1), Tile(4, 1)]))
        image = render.draw(self.picture(), CALIBRATION, overlay)
        center_y = 1 * 4 + 2
        middle = image.get(8 + 2 * 4 + 2, center_y)
        self.assertEqual(middle, render.LEG_COLORS[0])
        self.assertEqual(image.get(8 + 2 * 4 + 2, 3 * 4 + 2), BACKGROUND)   # nothing two rows down
        self.assertEqual(image.get(8 + 4 * 4 + 2, center_y), render.END_COLOR)

    def test_plain_picture_of_cells(self):
        image = render.plain_image(ROOM, tile_px=2)
        self.assertEqual((image.width, image.height), (12, 10))
        self.assertEqual(image.get(0, 0), render.WALL_COLOR)
        self.assertEqual(image.get(2, 2), render.OPEN_COLOR)
        self.assertEqual(image.get(4, 4), render.cell_color(ROOM.at(Tile(2, 2))))


class CommandLineTest(unittest.TestCase):
    MAP = os.path.join(REPO, "games", "bdsp", "maps", "route_202.json")

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(render.main(list(argv)), 0)
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
