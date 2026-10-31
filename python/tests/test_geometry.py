"""Tests for pokenav.geometry: directions, tiles and steps."""

import doctest
import unittest

from pokenav import geometry
from pokenav.geometry import CLOCKWISE, Direction, Tile


def load_tests(loader, tests, ignore):
    """Also runs the examples in the module's comments."""
    tests.addTests(doctest.DocTestSuite(geometry))
    return tests


class DirectionTest(unittest.TestCase):
    def test_offsets_have_y_growing_south(self):
        self.assertEqual((Direction.NORTH.dx, Direction.NORTH.dy), (0, -1))
        self.assertEqual((Direction.SOUTH.dx, Direction.SOUTH.dy), (0, 1))
        self.assertEqual((Direction.EAST.dx, Direction.EAST.dy), (1, 0))
        self.assertEqual((Direction.WEST.dx, Direction.WEST.dy), (-1, 0))

    def test_opposite(self):
        pairs = [
            (Direction.NORTH, Direction.SOUTH),
            (Direction.EAST, Direction.WEST),
        ]
        for a, b in pairs:
            self.assertIs(a.opposite, b)
            self.assertIs(b.opposite, a)

    def test_turn(self):
        self.assertIs(Direction.NORTH.turn(), Direction.EAST)
        self.assertIs(Direction.WEST.turn(), Direction.NORTH)
        self.assertIs(Direction.NORTH.turn(clockwise=False), Direction.WEST)
        for d in CLOCKWISE:
            self.assertIs(d.turn().turn(), d.opposite)

    def test_is_vertical(self):
        self.assertEqual([d.is_vertical for d in CLOCKWISE], [True, False, True, False])

    def test_parse_names_and_initials_in_any_case(self):
        cases = {
            "north": Direction.NORTH,
            "East": Direction.EAST,
            " S ": Direction.SOUTH,
            "w": Direction.WEST,
        }
        for text, expected in cases.items():
            self.assertIs(Direction.parse(text), expected, text)

    def test_parse_rejects_other_words(self):
        for text in ["", "up", "northeast", "x"]:
            with self.assertRaises(ValueError, msg=text):
                Direction.parse(text)


class TileTest(unittest.TestCase):
    def test_step(self):
        self.assertEqual(Tile(3, 4).step(Direction.NORTH), Tile(3, 3))
        self.assertEqual(Tile(3, 4).step(Direction.EAST, 2), Tile(5, 4))
        self.assertEqual(Tile(0, 0).step(Direction.WEST), Tile(-1, 0))
        self.assertEqual(Tile(1, 1).step(Direction.SOUTH, 0), Tile(1, 1))

    def test_manhattan(self):
        self.assertEqual(Tile(0, 0).manhattan(Tile(3, -4)), 7)
        self.assertEqual(Tile(2, 2).manhattan(Tile(2, 2)), 0)

    def test_direction_to(self):
        self.assertIs(Tile(5, 5).direction_to(Tile(5, 1)), Direction.NORTH)
        self.assertIs(Tile(5, 5).direction_to(Tile(9, 5)), Direction.EAST)
        self.assertIsNone(Tile(5, 5).direction_to(Tile(5, 5)))
        self.assertIsNone(Tile(5, 5).direction_to(Tile(6, 6)))

    def test_is_a_hashable_tuple(self):
        self.assertEqual({Tile(1, 2), Tile(1, 2)}, {Tile(1, 2)})
        self.assertEqual(Tile(1, 2), (1, 2))
        self.assertEqual(str(Tile(1, 2)), "(1, 2)")


if __name__ == "__main__":
    unittest.main()
