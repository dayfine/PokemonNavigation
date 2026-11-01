"""Tests for pokenav.decomp.repos, and the tiny checkouts the decomp tests
share: `write_platinum(root)` and `write_diamond(root)` lay out the same
two-cell world (Tiny Town west of Tiny Route) in each repository's files,
so a map generates the same from either."""

import json
import os
import struct
import tempfile
import unittest

from pokenav.decomp import landdata
from pokenav.decomp.repos import Diamond, Platinum, display_name, git_head, open_repo

#   The world: a 2 x 1 matrix, Tiny Town (land 1) west of Tiny Route (land 2).
TOWN, ROUTE, HOUSE = 1, 2, 3
PT_HEADERS = {TOWN: "MAP_HEADER_TINY_TOWN", ROUTE: "MAP_HEADER_TINY_ROUTE", HOUSE: "MAP_HEADER_TINY_HOUSE"}
DP_HEADERS = {TOWN: "MAP_TINY_TOWN", ROUTE: "MAP_TINY_ROUTE", HOUSE: "MAP_TINY_HOUSE"}

#   Tile attributes used by the fixtures.
WALL, OPEN, GRASS, CAVE, ONE_WAY = 0x8000, 0x0000, 0x0002, 0x0008, 0x0030
LEDGE_SOUTH, DOUBLE_NORTH, DOOR, WARP_NORTH, RIVER = 0x803B, 0x805A, 0x8069, 0x006E, 0x8010

#   Tiny Town's cell: walls around a room at x 10..15, z 10..15, a door in its
#   north wall, a ledge along its south side onto an open row, grass, a pond
#   and a stood-on warp in the room.
TOWN_TILES = {(x, z): OPEN for x in range(10, 16) for z in range(10, 16)}
TOWN_TILES.update({(12, 9): DOOR, (14, 14): GRASS, (15, 14): GRASS, (13, 13): RIVER, (15, 10): WARP_NORTH})
TOWN_TILES.update({(x, 16): LEDGE_SOUTH for x in range(10, 16)})
TOWN_TILES.update({(x, 17): OPEN for x in range(10, 16)})
#   Tiny Route's cell: open, with a blocked top row, a cave floor tile, a
#   one-way block and a two-tile ledge.
ROUTE_TILES = {(x, 0): WALL for x in range(32)}
ROUTE_TILES.update({(0, 5): CAVE, (1, 5): ONE_WAY, (2, 5): DOUBLE_NORTH})


def land_bytes(tiles, default):
    """A land data file: the header and 1024 attributes."""
    attrs = [tiles.get((x, z), default) for z in range(32) for x in range(32)]
    return struct.pack("<4I", 2048, 0, 0, 0) + struct.pack("<1024H", *attrs)


#   Tiny Town's objects, in each repository's terms: a trainer who looks
#   south, a kid wandering a tile around, a signboard, a Rock Smash rock, an
#   item ball, the rival hidden by a flag, and (Platinum only) a copy of a
#   Route object hidden behind the Route's header. The background events are
#   a wall sign and a hidden item.
PT_EVENTS = {
    "bg_events": [
        {"x": 15, "z": 15, "type": 1, "script": 77},
        {"x": 11, "z": 12, "type": 2, "script": 3},
    ],
    "object_events": [
        {"id": "LOCALID_GUARD", "graphics_id": "OBJ_EVENT_GFX_YOUNGSTER", "movement_type": "MOVEMENT_TYPE_LOOK_SOUTH",
         "trainer_type": "TRAINER_TYPE_NORMAL", "hidden_flag": "0", "script": 1, "initial_dir": 1, "data": [3],
         "movement_range_x": 0, "movement_range_z": 0, "x": 12, "z": 12, "y": 0},
        {"id": "LOCALID_KID", "graphics_id": "OBJ_EVENT_GFX_LASS", "movement_type": "MOVEMENT_TYPE_WANDER_AROUND",
         "trainer_type": "TRAINER_TYPE_NONE", "hidden_flag": "0", "script": 2, "initial_dir": 2, "data": [],
         "movement_range_x": 1, "movement_range_z": 1, "x": 11, "z": 11, "y": 0},
        {"id": "LOCALID_SIGNBOARD", "graphics_id": "OBJ_EVENT_GFX_SIGNBOARD", "movement_type": "MOVEMENT_TYPE_NONE",
         "trainer_type": "TRAINER_TYPE_NONE", "hidden_flag": "0", "script": 3, "initial_dir": 0, "data": [],
         "movement_range_x": 0, "movement_range_z": 0, "x": 10, "z": 10, "y": 0},
        {"id": "LOCALID_ROCK", "graphics_id": "OBJ_EVENT_GFX_ROCK_SMASH", "movement_type": "MOVEMENT_TYPE_NONE",
         "trainer_type": "TRAINER_TYPE_NONE", "hidden_flag": "0", "script": 0, "initial_dir": 0, "data": [],
         "movement_range_x": 0, "movement_range_z": 0, "x": 14, "z": 10, "y": 0},
        {"id": "LOCALID_POTION", "graphics_id": "OBJ_EVENT_GFX_POKEBALL", "movement_type": "MOVEMENT_TYPE_NONE",
         "trainer_type": "TRAINER_TYPE_NONE", "hidden_flag": "FLAG_OBTAINED_POTION", "script": 0, "initial_dir": 0,
         "data": [], "movement_range_x": 0, "movement_range_z": 0, "x": 11, "z": 15, "y": 0},
        {"id": "LOCALID_RIVAL", "graphics_id": "OBJ_EVENT_GFX_BARRY", "movement_type": "MOVEMENT_TYPE_LOOK_SOUTH_AND_EAST",
         "trainer_type": "TRAINER_TYPE_NONE", "hidden_flag": "FLAG_HIDE_RIVAL", "script": 0, "initial_dir": 1,
         "data": [], "movement_range_x": 0, "movement_range_z": 0, "x": 13, "z": 15, "y": 0},
        {"id": "LOCALID_COPY", "graphics_id": "OBJ_EVENT_GFX_LASS", "movement_type": "MOVEMENT_TYPE_LOOK_WEST",
         "trainer_type": "TRAINER_TYPE_NONE", "hidden_flag": "MAP_HEADER_TINY_ROUTE", "script": 0, "initial_dir": 2,
         "data": [], "movement_range_x": 0, "movement_range_z": 0, "x": 15, "z": 15, "y": 0},
    ],
    "warp_events": [{"x": 12, "z": 9, "dest_header_id": "MAP_HEADER_TINY_HOUSE", "dest_warp_id": 0}],
    "coord_events": [],
}

#   Diamond's sprite ids (include/constants/sprites.h), movement numbers and
#   flags for the same objects. Sprite 93, the signboard, is unnamed there.
BOY1, GIRL1, SIGNBOARD, BREAKROCK, MONSTARBALL, RIVEL = 3, 6, 93, 85, 87, 148
LOOK_SOUTH, WANDER_AROUND, LOOK_SOUTH_AND_EAST, NONE = 15, 3, 9, 0
DP_OBJECTS = [
    #   id, sprite, movement, trainer type, flag, script, facing, params, ranges, x, z, y
    (0, BOY1, LOOK_SOUTH, 1, 0, 1, 1, (3, 0, 0), 0, 0, 12, 12, 0),
    (1, GIRL1, WANDER_AROUND, 0, 0, 2, 2, (0, 0, 0), 1, 1, 11, 11, 0),
    (2, SIGNBOARD, NONE, 0, 0, 3, 0, (0, 0, 0), 0, 0, 10, 10, 0),
    (3, BREAKROCK, NONE, 0, 0, 0, 0, (0, 0, 0), 0, 0, 14, 10, 0),
    (4, MONSTARBALL, NONE, 0, 500, 0, 0, (0, 0, 0), 0, 0, 11, 15, 0),
    (5, RIVEL, LOOK_SOUTH_AND_EAST, 0, 400, 0, 1, (0, 0, 0), 0, 0, 13, 15, 0),
]
DP_SPRITES_H = "#define SPRITE_BOY1 3\n#define SPRITE_GIRL1 6\n#define SPRITE_BREAKROCK 85\n" \
               "#define SPRITE_MONSTARBALL 87\n#define SPRITE_RIVEL 148\n"
DP_MAPS_H = "#define MAP_TINY_TOWN 1 // T01\n#define MAP_TINY_ROUTE 2\n#define MAP_TINY_HOUSE 3\n"


def dp_object_bytes(record):
    (id_, sprite, movement, trainer, flag, script, facing, params, rx, rz, x, z, y) = record
    return struct.pack("<HHHHHHhHHHhhHHi", id_, sprite, movement, trainer, flag, script, facing,
                       *params, rx, rz, x, z, y << 16)


def dp_events_bytes(objects=DP_OBJECTS, warps=((12, 9, HOUSE, 0),), signs=((77, 1, 15, 15), (3, 2, 11, 12)), coords=1):
    data = struct.pack("<I", len(signs))
    for script, kind, x, z in signs:
        data += struct.pack("<HHIIiI", script, kind, x, z, 0, 4)
    data += struct.pack("<I", len(objects)) + b"".join(dp_object_bytes(o) for o in objects)
    data += struct.pack("<I", len(warps)) + b"".join(struct.pack("<HHHHi", *w, 0) for w in warps)
    data += struct.pack("<I", coords) + bytes(16 * coords)
    return data


def dp_matrix_bytes(name="tiny", maps=(TOWN, ROUTE), headers=(TOWN, ROUTE), width=2, height=1):
    data = struct.pack("<5B", width, height, 1, 1, len(name)) + name.encode()
    data += struct.pack("<%dH" % len(headers), *headers)
    data += bytes(width * height)
    return data + struct.pack("<%dH" % len(maps), *maps)


def _write(root, relative, data):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(path, mode) as f:
        f.write(data)


def write_platinum(root):
    """A pokeplatinum checkout with the tiny world."""
    _write(root, "res/field/maps/data/map_data_001.bin", land_bytes(TOWN_TILES, WALL))
    _write(root, "res/field/maps/data/map_data_002.bin", land_bytes(ROUTE_TILES, OPEN))
    _write(root, "res/field/matrices/map_matrix_000.json", json.dumps({
        "name": "tiny", "headers": [[PT_HEADERS[TOWN], PT_HEADERS[ROUTE]]],
        "altitudes": [[0, 0]], "maps": [["MAP_001", "MAP_002"]]}))
    _write(root, "res/field/events/events_tiny_town.json", json.dumps(PT_EVENTS))
    _write(root, "res/field/events/events_tiny_route.json", json.dumps(
        {"bg_events": [], "object_events": [], "warp_events": [], "coord_events": []}))


def write_diamond(root):
    """A pokediamond checkout with the tiny world."""
    _write(root, "files/fielddata/land_data/land_data_release/narc_0001.bin", land_bytes(TOWN_TILES, WALL))
    _write(root, "files/fielddata/land_data/land_data_release/narc_0002.bin", land_bytes(ROUTE_TILES, OPEN))
    _write(root, "files/fielddata/mapmatrix/map_matrix/narc_0000.bin", dp_matrix_bytes())
    _write(root, "files/fielddata/eventdata/zone_event_release/narc_0010.bin", dp_events_bytes())
    _write(root, "files/fielddata/eventdata/zone_event_release/narc_0011.bin", dp_events_bytes([], (), (), 0))
    _write(root, "include/constants/sprites.h", DP_SPRITES_H)
    _write(root, "include/constants/maps.h", DP_MAPS_H)


class DisplayNameTest(unittest.TestCase):
    def test_constants_become_place_names(self):
        self.assertEqual(display_name("MAP_HEADER_ROUTE_201"), "Route 201")
        self.assertEqual(display_name("MAP_ROUTE_204_SOUTH"), "Route 204 South")
        self.assertEqual(display_name("MAP_HEADER_SANDGEM_TOWN"), "Sandgem Town")
        self.assertEqual(display_name("MAP_SANDGEM"), "Sandgem Town")
        self.assertEqual(display_name("MAP_JUBLIFE"), "Jubilife City")
        self.assertEqual(display_name("MAP_JUBLIFE_POKECENTER_1F"), "Jubilife Pokecenter 1F")
        self.assertEqual(display_name("MAP_HEADER_JUBILIFE_TV_1F"), "Jubilife TV 1F")


class GitHeadTest(unittest.TestCase):
    def test_reads_a_detached_head_a_ref_and_packed_refs(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(git_head(root), "")
            _write(root, ".git/HEAD", "abc123\n")
            self.assertEqual(git_head(root), "abc123")
            _write(root, ".git/HEAD", "ref: refs/heads/main\n")
            self.assertEqual(git_head(root), "")
            _write(root, ".git/packed-refs", "# pack-refs\ndef456 refs/heads/main\n")
            self.assertEqual(git_head(root), "def456")
            _write(root, ".git/refs/heads/main", "789abc\n")
            self.assertEqual(git_head(root), "789abc")


class PlatinumTest(unittest.TestCase):
    def test_reads_the_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            write_platinum(root)
            repo = open_repo("pokeplatinum", root, "c668969")
            self.assertIsInstance(repo, Platinum)
            self.assertEqual((repo.repository, repo.commit), ("pret/pokeplatinum", "c668969"))
            matrix = repo.matrix(0)
            self.assertEqual((matrix.maps[0], matrix.headers[0]), ([1, 2], [PT_HEADERS[TOWN], PT_HEADERS[ROUTE]]))
            self.assertEqual(landdata.cell(repo.land(TOWN)[9 * 32 + 12]).behavior.value, "door")
            events = repo.events("tiny_town")
            self.assertEqual([o.name for o in events.objects][:3], ["guard", "kid", "signboard"])
            self.assertEqual(events.warps[0].to_map, PT_HEADERS[HOUSE])
            self.assertEqual(repo.events("res/field/events/events_tiny_route.json").objects, [])
            self.assertEqual(repo.map_name(PT_HEADERS[HOUSE]), "Tiny House")
            self.assertEqual(repo.land_path(5), "res/field/maps/data/map_data_005.bin")


class DiamondTest(unittest.TestCase):
    def test_reads_the_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            write_diamond(root)
            repo = open_repo("pokediamond", root)
            self.assertIsInstance(repo, Diamond)
            self.assertEqual(repo.commit, "")
            matrix = repo.matrix(0)
            self.assertEqual((matrix.name, matrix.maps[0], matrix.headers[0]),
                             ("tiny", [1, 2], [DP_HEADERS[TOWN], DP_HEADERS[ROUTE]]))
            self.assertEqual(repo.land(TOWN), landdata.attributes(land_bytes(TOWN_TILES, WALL)))
            events = repo.events("10")
            self.assertEqual([o.graphic for o in events.objects], ["BOY1", "GIRL1", "SIGNBOARD", "BREAKROCK",
                                                                   "MONSTARBALL", "RIVEL"])
            self.assertEqual(events.warps[0].to_map, DP_HEADERS[HOUSE])
            self.assertEqual(events.signs[0].script, 77)
            self.assertEqual(repo.sprite_names()[91], "MAP_SIGNPOST")
            self.assertEqual(repo.map_ids()[3], DP_HEADERS[HOUSE])
            self.assertEqual(repo.events_path("327"), "files/fielddata/eventdata/zone_event_release/narc_0327.bin")

    def test_unknown_repository(self):
        with self.assertRaises(ValueError):
            open_repo("pokeemerald", "/nowhere")


if __name__ == "__main__":
    unittest.main()
