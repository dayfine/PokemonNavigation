"""Tests for pokenav.grid.maps.render: the text form (snapshots) and drawing on
a picture lined up with the grid."""

import unittest

from pokenav.grid.geometry import Tile
from pokenav.grid.maps import render
from pokenav.grid.maps.render import Overlay
from pokenav.grid.maps.schema import MapImage
from pokenav.grid.maps.textgrid import parse
from pokenav.png import Image

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


if __name__ == "__main__":
    unittest.main()
