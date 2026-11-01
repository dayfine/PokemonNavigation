"""Tests for pokenav.decomp.landdata: tile attributes, cells and matrices."""

import struct
import unittest

from pokenav.decomp import landdata
from pokenav.decomp.landdata import LandGrid, matrix_from_binary, matrix_from_json
from pokenav.grid.maps.model import Behavior, Cell

from tests.test_decomp_repos import (DOOR, DOUBLE_NORTH, GRASS, LEDGE_SOUTH, OPEN, RIVER, ROUTE_TILES, TOWN_TILES,
                                     WALL, WARP_NORTH, dp_matrix_bytes, land_bytes)


class AttributesTest(unittest.TestCase):
    def test_reads_the_tiles_after_the_header(self):
        attrs = landdata.attributes(land_bytes(TOWN_TILES, WALL))
        self.assertEqual(len(attrs), 1024)
        self.assertEqual(attrs[9 * 32 + 12], DOOR)
        self.assertEqual(attrs[0], WALL)

    def test_rejects_a_wrong_header_or_a_short_file(self):
        good = land_bytes({}, OPEN)
        with self.assertRaisesRegex(ValueError, "2048"):
            landdata.attributes(struct.pack("<4I", 1024, 0, 0, 0) + good[16:])
        with self.assertRaisesRegex(ValueError, "fewer"):
            landdata.attributes(good[:-2])


class CellTest(unittest.TestCase):
    def test_collision_and_behaviors(self):
        cases = {
            OPEN: Cell(),
            WALL: Cell(blocked=True),
            GRASS: Cell(behavior=Behavior.TALL_GRASS),
            0x8002: Cell(blocked=True, behavior=Behavior.TALL_GRASS),
            0x0010: Cell(blocked=True, behavior=Behavior.WATER),      # water blocks whatever its bit says
            RIVER: Cell(blocked=True, behavior=Behavior.WATER),
            0x003B: Cell(blocked=True, behavior=Behavior.LEDGE_SOUTH),  # so do ledges
            LEDGE_SOUTH: Cell(blocked=True, behavior=Behavior.LEDGE_SOUTH),
            0x8038: Cell(blocked=True, behavior=Behavior.LEDGE_EAST),
            DOUBLE_NORTH: Cell(blocked=True, behavior=Behavior.LEDGE_NORTH),
            DOOR: Cell(blocked=True, behavior=Behavior.DOOR),
            0x8062: Cell(blocked=True, behavior=Behavior.DOOR),       # a cave mouth
            WARP_NORTH: Cell(behavior=Behavior.WARP),
            0x806F: Cell(behavior=Behavior.WARP),                     # warp tiles are stood on
            0x005E: Cell(behavior=Behavior.WARP),
            0x0020: Cell(behavior=Behavior.ICE),
            0x0040: Cell(behavior=Behavior.FORCED_EAST),
            0x0008: Cell(),                                           # cave floor is plain ground
            0x0021: Cell(),                                           # so is sand
            0x0030: Cell(),                                           # and a one-way block, for now
            0x8080: Cell(blocked=True),                               # a table
        }
        for attr, expected in cases.items():
            self.assertEqual(landdata.cell(attr), expected, hex(attr))

    def test_cave_floor(self):
        self.assertTrue(landdata.is_cave_floor(0x0008))
        self.assertTrue(landdata.is_cave_floor(0x8008))
        self.assertFalse(landdata.is_cave_floor(OPEN))


class MatrixTest(unittest.TestCase):
    def test_from_json(self):
        matrix = matrix_from_json({"name": "m", "headers": [["MAP_HEADER_A", "MAP_HEADER_B"], ["MAP_HEADER_B", "MAP_HEADER_EVERYWHERE"]],
                                   "maps": [["MAP_005", "MAP_006"], ["MAP_007", "MAP_NONE"]]})
        self.assertEqual((matrix.width, matrix.height), (2, 2))
        self.assertEqual(matrix.maps, [[5, 6], [7, None]])
        self.assertEqual(matrix.header_at(1, 0), "MAP_HEADER_B")
        self.assertIsNone(matrix.header_at(2, 0))
        self.assertEqual(matrix.cells_of("MAP_HEADER_B"), [(0, 1), (1, 0)])
        self.assertEqual(matrix.origin_of("MAP_HEADER_B"), (0, 0))
        self.assertEqual(matrix.origin_of("MAP_HEADER_A"), (0, 0))
        self.assertIsNone(matrix.origin_of("MAP_HEADER_C"))

    def test_from_json_without_headers(self):
        matrix = matrix_from_json({"name": "cave", "headers": [], "maps": [["MAP_435"], ["MAP_436"]]})
        self.assertEqual(matrix.maps, [[435], [436]])
        self.assertEqual(matrix.headers, [[None], [None]])

    def test_from_binary(self):
        data = dp_matrix_bytes("m", maps=(5, 6, 7, 0xFFFF), headers=(1, 2, 2, 9), width=2, height=2)
        matrix = matrix_from_binary(data, {1: "MAP_A", 2: "MAP_B"})
        self.assertEqual((matrix.name, matrix.maps), ("m", [[5, 6], [7, None]]))
        self.assertEqual(matrix.headers, [["MAP_A", "MAP_B"], ["MAP_B", "MAP_9"]])

    def test_from_binary_without_tables(self):
        data = struct.pack("<5B", 1, 2, 0, 0, 1) + b"c" + struct.pack("<2H", 412, 413)
        matrix = matrix_from_binary(data, {})
        self.assertEqual((matrix.maps, matrix.headers), ([[412], [413]], [[None], [None]]))


class LandGridTest(unittest.TestCase):
    def test_looks_tiles_up_across_cells(self):
        land = LandGrid()
        land.add(0, 0, landdata.attributes(land_bytes(TOWN_TILES, WALL)))
        land.add(0, 1, landdata.attributes(land_bytes(ROUTE_TILES, OPEN)))
        self.assertEqual(land.attribute(12, 9), DOOR)
        self.assertEqual(land.attribute(32, 0), WALL)
        self.assertEqual(land.attribute(34, 5), DOUBLE_NORTH)
        self.assertIsNone(land.attribute(64, 0))
        self.assertIsNone(land.attribute(0, 32))
        self.assertIsNone(land.attribute(-1, 0))
        self.assertEqual(land.bounds(), (0, 0, 64, 32))
        self.assertEqual(land.cells(), [(0, 0), (0, 1)])

    def test_errors(self):
        land = LandGrid()
        with self.assertRaises(ValueError):
            land.bounds()
        with self.assertRaisesRegex(ValueError, "1024"):
            land.add(0, 0, [OPEN] * 10)


if __name__ == "__main__":
    unittest.main()
