"""Tests for pokenav.grid.maps.objects (sight, signs, blocking, anchors) and the
world's screen coverage."""

import unittest

from pokenav.games import frlg
from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.objects import (
    Blocking, blocking_tiles, can_read, is_corner, reading_tile, sight_tiles,
    walls_around, watched_tiles,
)
from pokenav.grid.maps.schema import Connection, MapFile, Npc, Sign, Wander
from pokenav.grid.maps.textgrid import parse
from pokenav.grid.maps.world import Place, World

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST

#   Row 2 is a ledge with a gap at x = 4; a sign at (1, 4); an NPC at (3, 4).
SMALL = parse("""\
#..?..#
#..\"\".#
#vvv..#
#.....#
#S.N..#
""")


class SightTest(unittest.TestCase):
    def test_a_ledge_ends_the_line(self):
        trainer = Npc("npc", Tile(3, 4), N, sight=4)
        self.assertEqual(sight_tiles(SMALL.grid, trainer), [Tile(3, 3)])

    def test_range_walls_and_other_objects(self):
        grid = SMALL.grid
        self.assertEqual(sight_tiles(grid, Npc("a", Tile(1, 3), E, sight=2)), [Tile(2, 3), Tile(3, 3)])
        self.assertEqual(sight_tiles(grid, Npc("a", Tile(1, 3), E, sight=9)),
                         [Tile(x, 3) for x in range(2, 6)])
        self.assertEqual(sight_tiles(grid, Npc("a", Tile(1, 3), E, sight=9), {Tile(4, 3)}),
                         [Tile(2, 3), Tile(3, 3)])

    def test_not_a_trainer(self):
        self.assertEqual(sight_tiles(SMALL.grid, Npc("a", Tile(3, 4), N)), [])
        self.assertEqual(sight_tiles(SMALL.grid, Npc("a", Tile(3, 4), None, sight=3)), [])

    def test_watched_tiles_name_the_trainers(self):
        map_file = MapFile(SMALL.grid, npcs=[
            Npc("up", Tile(4, 4), N, sight=2),
            Npc("left", Tile(5, 3), W, sight=1),
        ])
        self.assertEqual(watched_tiles(map_file), {
            Tile(4, 3): ["up", "left"],
            Tile(4, 2): ["up"],
        })


class SignTest(unittest.TestCase):
    def test_read_from_the_tile_it_faces(self):
        sign = Sign("board", Tile(1, 4), N)
        self.assertEqual(reading_tile(sign), Tile(1, 5))
        self.assertTrue(can_read(sign, Tile(1, 5), N))
        self.assertFalse(can_read(sign, Tile(1, 5), E))
        self.assertFalse(can_read(sign, Tile(2, 4), W))
        side_sign = Sign("post", Tile(1, 4), W)
        self.assertTrue(can_read(side_sign, Tile(2, 4), W))


class BlockingTest(unittest.TestCase):
    def test_policies(self):
        map_file = MapFile(SMALL.grid, npcs=[
            Npc("guard", Tile(3, 4)),
            Npc("kid", Tile(4, 1), wander=Wander(Tile(4, 0), Tile(5, 1))),
        ])
        self.assertEqual(blocking_tiles(map_file, Blocking.NONE), set())
        self.assertEqual(blocking_tiles(map_file, Blocking.STATIC), {Tile(3, 4)})
        self.assertEqual(blocking_tiles(map_file, Blocking.ALL),
                         {Tile(3, 4), Tile(4, 0), Tile(5, 0), Tile(4, 1), Tile(5, 1)})


class AnchorTest(unittest.TestCase):
    def test_walls_around(self):
        grid = SMALL.grid
        self.assertEqual(walls_around(grid, Tile(1, 1)), [W])           # the ledge below is a hop
        self.assertEqual(walls_around(grid, Tile(1, 3)), [N, S, W])     # ledge, sign, wall
        self.assertEqual(walls_around(grid, Tile(4, 1)), [])           # grass, gap, open
        self.assertEqual(walls_around(grid, Tile(2, 3), objects={Tile(3, 3)}), [N])

    def test_corners_are_anchors(self):
        grid = SMALL.grid
        self.assertTrue(is_corner(grid, Tile(1, 3)))
        self.assertFalse(is_corner(grid, Tile(1, 1)))
        self.assertFalse(is_corner(grid, Tile(3, 3)))      # only the ledge, north
        self.assertFalse(is_corner(parse("#.#\n").grid, Tile(1, 0)))  # walls east and west


class ScreenCoverageTest(unittest.TestCase):
    def test_a_small_room_shows_black_at_its_walls(self):
        house = parse("######\n#....#\n#....#\n#....#\n#....#\n######\n", name="House")
        world = World([house])
        self.assertGreater(world.off_map_fraction(Place("House", Tile(1, 1)), frlg.VIEWPORT), 0.5)

    def test_connected_maps_count_as_shown(self):
        route = parse((("." * 20) + "\n") * 40, name="Route")
        route.connections = [Connection(N, "Town", 0)]
        town = parse((("." * 20) + "\n") * 20, name="Town")
        town.connections = [Connection(S, "Route", 0)]
        world = World([route, town])
        viewport = frlg.VIEWPORT
        self.assertEqual(world.off_map_fraction(Place("Route", Tile(10, 20)), viewport), 0)
        #   At the north edge the town fills the rows above.
        self.assertEqual(world.off_map_fraction(Place("Route", Tile(10, 0)), viewport), 0)
        #   At the south edge, nothing is connected: 5 of 10 rows are black.
        self.assertEqual(world.off_map_fraction(Place("Route", Tile(10, 39)), viewport), 0.5)


if __name__ == "__main__":
    unittest.main()
