"""Tests for pokenav.grid.maps.pret and the FRLG game data.

Most tests build a tiny checkout in pret's file formats in a temporary
directory. The tests at the end read a real pokefirered checkout when the
environment variable POKEFIRERED_DIR points at one, and are skipped
otherwise (pret data is not committed here).
"""

import json
import os
import struct
import tempfile
import unittest

from pokenav.games import frlg
from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.model import Behavior, Cell
from pokenav.grid.maps.pret import Checkout, PretGame, tileset_dir
from pokenav.grid.maps.schema import Connection, Wander, Warp
from pokenav.grid.maps.world import Place
from pokenav.grid.movement import WorldState, world_walk

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST

#   The fixture's primary tileset has 4 metatiles: normal, tall grass, a
#   south ledge and a door. Its secondary tileset has pond water and a sign.
NORMAL, GRASS, LEDGE, DOOR, POND, SIGNPOST = range(6)
PRIMARY_BEHAVIORS = [0x00, 0x02, 0x3B, 0x69]
SECONDARY_BEHAVIORS = [0x10, 0x84]
TINY_GAME = PretGame(primary_metatiles=len(PRIMARY_BEHAVIORS), behaviors=frlg.BEHAVIORS)


def block(metatile, collision=0, elevation=3):
    """One map.bin entry."""
    return metatile | (collision << 10) | (elevation << 12)


#   TinyTown's 4 x 3 blocks, top row first.
TINY_BLOCKS = [
    [block(NORMAL, 1, 0), block(DOOR, 1), block(NORMAL), block(SIGNPOST, 1)],
    [block(NORMAL), block(GRASS), block(NORMAL), block(POND)],
    [block(LEDGE, 0, 0), block(LEDGE, 0, 0), block(NORMAL), block(NORMAL, 0, 15)],
]

TINY_TOWN = {
    "id": "MAP_TINY_TOWN",
    "layout": "LAYOUT_TINY",
    "connections": [
        {"map": "MAP_ROUTE9", "offset": -2, "direction": "down"},
        {"map": "MAP_UNDERWATER", "offset": 0, "direction": "dive"},
    ],
    "object_events": [
        {"local_id": "LOCALID_GUARD", "x": 2, "y": 1, "movement_type": "MOVEMENT_TYPE_FACE_DOWN",
         "trainer_type": "TRAINER_TYPE_NORMAL", "trainer_sight_or_berry_tree_id": "3", "flag": "0"},
        {"x": 0, "y": 1, "movement_type": "MOVEMENT_TYPE_WANDER_UP_AND_DOWN",
         "movement_range_x": 2, "movement_range_y": 1, "trainer_type": "TRAINER_TYPE_NONE",
         "trainer_sight_or_berry_tree_id": "0", "flag": "FLAG_HIDE_KID"},
    ],
    "warp_events": [{"x": 1, "y": 0, "elevation": 0, "dest_map": "MAP_TINY_HOUSE", "dest_warp_id": "0"}],
    "bg_events": [
        {"type": "sign", "x": 3, "y": 0, "player_facing_dir": "BG_EVENT_PLAYER_FACING_ANY", "script": "Tiny_Sign"},
        {"type": "hidden_item", "x": 2, "y": 2},
    ],
}

TINY_HOUSE = {"id": "MAP_TINY_HOUSE", "layout": "LAYOUT_TINY",
              "warp_events": [{"x": 2, "y": 2, "dest_map": "MAP_TINY_TOWN", "dest_warp_id": "0"}]}


def write_fixture(root):
    """Writes a two-map pret-format checkout under `root`."""
    def write(path, data):
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(full, mode) as f:
            f.write(data)

    layout = {"id": "LAYOUT_TINY", "width": 4, "height": 3,
              "primary_tileset": "gTileset_General", "secondary_tileset": "gTileset_TinyTown1",
              "blockdata_filepath": "data/layouts/Tiny/map.bin"}
    write("data/layouts/layouts.json", json.dumps({"layouts": [layout, {}]}))
    blocks = [b for row in TINY_BLOCKS for b in row]
    write("data/layouts/Tiny/map.bin", struct.pack("<%dH" % len(blocks), *blocks))
    write("data/tilesets/primary/general/metatile_attributes.bin",
          struct.pack("<4I", *PRIMARY_BEHAVIORS))
    write("data/tilesets/secondary/tiny_town_1/metatile_attributes.bin",
          struct.pack("<2I", *SECONDARY_BEHAVIORS))
    write("data/maps/TinyTown/map.json", json.dumps(TINY_TOWN))
    write("data/maps/TinyHouse/map.json", json.dumps(TINY_HOUSE))


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        write_fixture(self._tmp.name)
        self.checkout = Checkout(self._tmp.name, TINY_GAME)
        self.town = self.checkout.load_map("TinyTown")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cells(self):
        grid = self.town.grid
        expected = {
            Tile(0, 0): Cell(blocked=True, elevation=0),
            Tile(1, 0): Cell(blocked=True, elevation=3, behavior=Behavior.DOOR),
            Tile(3, 0): Cell(blocked=True, elevation=3, behavior=Behavior.SIGN),
            Tile(1, 1): Cell(elevation=3, behavior=Behavior.TALL_GRASS),
            Tile(3, 1): Cell(blocked=True, elevation=3, behavior=Behavior.WATER),   # water always blocks
            Tile(0, 2): Cell(elevation=0, behavior=Behavior.LEDGE_SOUTH),
            Tile(3, 2): Cell(elevation=15),
        }
        self.assertEqual((grid.name, grid.width, grid.height), ("TinyTown", 4, 3))
        for tile, cell in expected.items():
            self.assertEqual(grid.at(tile), cell, tile)

    def test_objects(self):
        guard, kid = self.town.npcs
        self.assertEqual((guard.name, guard.tile, guard.facing, guard.sight),
                         ("LOCALID_GUARD", Tile(2, 1), S, 3))
        self.assertIsNone(guard.wander)
        self.assertEqual(kid.name, "object_1")
        self.assertEqual(kid.wander, Wander(Tile(0, 0), Tile(0, 2)))   # up and down only
        self.assertIn("hidden by FLAG_HIDE_KID", kid.note)
        self.assertEqual(len(self.town.signs), 1)
        self.assertEqual((self.town.signs[0].tile, self.town.signs[0].facing), (Tile(3, 0), N))

    def test_warps_and_connections(self):
        self.assertEqual(self.town.warps, [Warp(Tile(1, 0), "TinyHouse", 0)])
        #   Route 9 is not in the checkout: its id is kept. Dive is skipped.
        self.assertEqual(self.town.connections, [Connection(S, "MAP_ROUTE9", -2)])

    def test_world(self):
        world = self.checkout.load_world(["TinyTown", "TinyHouse"])
        arrival = world.warp_arrival(Place("TinyTown", Tile(1, 0)), N)
        self.assertEqual(arrival.place, Place("TinyHouse", Tile(2, 2)))

    def test_bad_map_bin_size(self):
        with open(os.path.join(self._tmp.name, "data/layouts/Tiny/map.bin"), "ab") as f:
            f.write(b"\0\0")
        with self.assertRaises(ValueError):
            Checkout(self._tmp.name, TINY_GAME).load_map("TinyTown")


class TilesetDirTest(unittest.TestCase):
    def test_names(self):
        cases = {
            "gTileset_General": "general",
            "gTileset_PalletTown": "pallet_town",
            "gTileset_GenericBuilding1": "generic_building_1",
            "gTileset_PokemonCenter": "pokemon_center",
        }
        for tileset, directory in cases.items():
            self.assertEqual(tileset_dir(tileset), directory)


POKEFIRERED = os.environ.get("POKEFIRERED_DIR", "")


@unittest.skipUnless(POKEFIRERED and os.path.isdir(POKEFIRERED), "set POKEFIRERED_DIR to a pokefirered checkout")
class PokefireredTest(unittest.TestCase):
    """Facts about the real maps, as decoded for issue #7's Route 1 fixture."""

    @classmethod
    def setUpClass(cls):
        checkout = Checkout(POKEFIRERED, frlg.PRET)
        cls.world = checkout.load_world(["Route1", "PalletTown", "ViridianCity", "PalletTown_PlayersHouse_1F"])

    def test_route1_size_and_ledges(self):
        route1 = self.world.grid("Route1")
        self.assertEqual((route1.width, route1.height), (24, 40))
        ledges = [t for t in route1.tiles() if route1.at(t).behavior is Behavior.LEDGE_SOUTH]
        ledge_rows = sorted({t.y for t in ledges})
        self.assertEqual(ledge_rows, [5, 10, 15, 20, 26, 31])

    def test_viridian_joins_route1_twelve_tiles_over(self):
        self.assertEqual(self.world.across_edge(Place("ViridianCity", Tile(22, 40))), Place("Route1", Tile(10, 0)))

    def test_walk_south_from_viridian(self):
        start = WorldState(Place("ViridianCity", Tile(22, 31)), 3)
        walked = world_walk(self.world, start, S, frlg.ELEVATION_RULES)
        #   Through Viridian's ledge gap, onto Route 1, over the row-5 ledge
        #   and through the grass, to the wall above the row-15 ledge.
        self.assertEqual(walked.state.place, Place("Route1", Tile(10, 14)))
        self.assertTrue(walked.held)

    def test_screen_coverage(self):
        house = Place("PalletTown_PlayersHouse_1F", Tile(5, 5))
        self.assertGreater(self.world.off_map_fraction(house, frlg.VIEWPORT), 0)
        self.assertEqual(self.world.off_map_fraction(Place("Route1", Tile(12, 20)), frlg.VIEWPORT), 0)


if __name__ == "__main__":
    unittest.main()
