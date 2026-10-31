"""Import maps from a pret decompilation checkout (pokefirered and its
relatives) into map files and a world.

pret data is not in this repository (pokefirered has no license file), so
the importer reads a local checkout. It reads:

- `data/layouts/layouts.json`: each layout's size, tilesets and `map.bin`;
- `map.bin`: one little-endian u16 per tile, bits 0-9 the metatile, 10-11
  collision, 12-15 elevation (include/global.fieldmap.h);
- `data/tilesets/{primary,secondary}/<name>/metatile_attributes.bin`: one
  u32 per metatile, bits 0-8 the behavior (src/fieldmap.c);
- `data/maps/<Map>/map.json`: connections, warps, objects and signs.

The behavior numbers and the primary tileset's size differ between games, so
the caller passes a `PretGame` (FRLG's is `pokenav.games.frlg.PRET`).

    checkout = Checkout("/path/to/pokefirered", frlg.PRET)
    route1 = checkout.load_map("Route1")         # a MapFile
    world = checkout.load_world(["Route1", "PalletTown"])
"""

import json
import os
import re
import struct
from typing import Dict, Iterable, List, Mapping, NamedTuple, Optional

from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.model import Behavior, Cell, GridMap2D
from pokenav.grid.maps.schema import Connection, MapFile, Note, Npc, Sign, Wander, Warp
from pokenav.grid.maps.world import World

#   map.bin fields (include/global.fieldmap.h).
METATILE_MASK = 0x03FF
COLLISION_MASK = 0x0C00
COLLISION_SHIFT = 10
ELEVATION_MASK = 0xF000
ELEVATION_SHIFT = 12
#   metatile_attributes.bin: the behavior is bits 0-8 (src/fieldmap.c).
BEHAVIOR_MASK = 0x01FF

#   pret's connection directions; "dive" and "emerge" are not walked.
CONNECTION_DIRECTIONS = {
    "up": Direction.NORTH, "down": Direction.SOUTH,
    "left": Direction.WEST, "right": Direction.EAST,
}

#   Movement types of standing NPCs that face one way.
FACING_MOVEMENTS = {
    "MOVEMENT_TYPE_FACE_UP": Direction.NORTH,
    "MOVEMENT_TYPE_FACE_DOWN": Direction.SOUTH,
    "MOVEMENT_TYPE_FACE_LEFT": Direction.WEST,
    "MOVEMENT_TYPE_FACE_RIGHT": Direction.EAST,
}

#   Movement types of wandering NPCs, and which ranges (x, y) they use.
WANDER_MOVEMENTS = {
    "MOVEMENT_TYPE_WANDER_AROUND": (True, True),
    "MOVEMENT_TYPE_WANDER_UP_AND_DOWN": (False, True),
    "MOVEMENT_TYPE_WANDER_LEFT_AND_RIGHT": (True, False),
}

#   bg_event facings for signs. "Any" is read from below, facing north, like
#   most signs; the note on the sign says it can be read from any side.
SIGN_FACINGS = {
    "BG_EVENT_PLAYER_FACING_NORTH": Direction.NORTH,
    "BG_EVENT_PLAYER_FACING_SOUTH": Direction.SOUTH,
    "BG_EVENT_PLAYER_FACING_EAST": Direction.EAST,
    "BG_EVENT_PLAYER_FACING_WEST": Direction.WEST,
    "BG_EVENT_PLAYER_FACING_ANY": Direction.NORTH,
}

#   Behaviors that can never be walked on, whatever their collision bits.
ALWAYS_BLOCKED = frozenset({Behavior.WATER})


class PretGame(NamedTuple):
    """What differs between pret games: how many metatiles the primary
    tileset has, and what each behavior number means."""

    primary_metatiles: int
    behaviors: Mapping[int, Behavior]


class Layout(NamedTuple):
    """One entry of layouts.json."""

    width: int
    height: int
    primary_tileset: str
    secondary_tileset: str
    blockdata: str


class Checkout:
    """A local pret checkout to import maps from."""

    def __init__(self, root: str, game: PretGame):
        self.root = root
        self.game = game
        self._layouts: Optional[Dict[str, Layout]] = None
        self._attributes: Dict[str, List[int]] = {}
        self._names: Optional[Dict[str, str]] = None

    def load_map(self, name: str) -> MapFile:
        """The map file for map `name`, as in data/maps/<name>/map.json."""
        header = self._read_json("data", "maps", name, "map.json")
        grid = GridMap2D(name, self._cells(self._layout(header["layout"])))
        return MapFile(
            grid=grid,
            game="pret",
            npcs=[_npc(i, event) for i, event in enumerate(header.get("object_events") or [])],
            signs=[_sign(i, event) for i, event in enumerate(header.get("bg_events") or [])
                   if event.get("type") == "sign"],
            warps=[self._warp(event) for event in header.get("warp_events") or []],
            connections=[self._connection(c) for c in header.get("connections") or []
                         if c["direction"] in CONNECTION_DIRECTIONS],
            notes=[Note("imported from data/maps/%s/map.json and its layout" % name, "pret")],
        )

    def load_world(self, names: Iterable[str]) -> World:
        return World(self.load_map(name) for name in names)

    def map_names(self) -> Dict[str, str]:
        """Map ids (MAP_PALLET_TOWN) to map names (PalletTown), for the maps
        in the checkout."""
        names = {}
        maps_dir = os.path.join(self.root, "data", "maps")
        for name in sorted(os.listdir(maps_dir)):
            path = os.path.join(maps_dir, name, "map.json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    names[json.load(f)["id"]] = name
        return names

    #   ---- cells ----

    def _cells(self, layout: Layout) -> List[List[Cell]]:
        with open(os.path.join(self.root, layout.blockdata), "rb") as f:
            data = f.read()
        count = layout.width * layout.height
        if len(data) != 2 * count:
            raise ValueError("%s has %d bytes for %d tiles" % (layout.blockdata, len(data), count))
        blocks = struct.unpack("<%dH" % count, data)
        cells = [self._cell(block, layout) for block in blocks]
        return [cells[y * layout.width:(y + 1) * layout.width] for y in range(layout.height)]

    def _cell(self, block: int, layout: Layout) -> Cell:
        behavior = self.game.behaviors.get(self._behavior_number(block & METATILE_MASK, layout), Behavior.NONE)
        collision = (block & COLLISION_MASK) >> COLLISION_SHIFT
        return Cell(blocked=bool(collision) or behavior in ALWAYS_BLOCKED,
                    elevation=(block & ELEVATION_MASK) >> ELEVATION_SHIFT,
                    behavior=behavior)

    def _behavior_number(self, metatile: int, layout: Layout) -> int:
        primary = self.game.primary_metatiles
        if metatile < primary:
            attributes = self._tileset_attributes(layout.primary_tileset, "primary")
        else:
            attributes = self._tileset_attributes(layout.secondary_tileset, "secondary")
            metatile -= primary
        if metatile >= len(attributes):
            return 0
        return attributes[metatile] & BEHAVIOR_MASK

    def _tileset_attributes(self, tileset: str, kind: str) -> List[int]:
        if tileset not in self._attributes:
            path = os.path.join(self.root, "data", "tilesets", kind, tileset_dir(tileset),
                                "metatile_attributes.bin")
            with open(path, "rb") as f:
                data = f.read()
            self._attributes[tileset] = list(struct.unpack("<%dI" % (len(data) // 4), data))
        return self._attributes[tileset]

    #   ---- headers ----

    def _layout(self, layout_id: str) -> Layout:
        if self._layouts is None:
            table = self._read_json("data", "layouts", "layouts.json")
            self._layouts = {entry["id"]: Layout(
                entry["width"], entry["height"], entry["primary_tileset"],
                entry["secondary_tileset"], entry["blockdata_filepath"],
            ) for entry in table["layouts"] if "id" in entry}
        return self._layouts[layout_id]

    def _warp(self, event: Mapping) -> Warp:
        return Warp(Tile(event["x"], event["y"]), self._map_name(event["dest_map"]), int(event["dest_warp_id"]))

    def _connection(self, data: Mapping) -> Connection:
        return Connection(CONNECTION_DIRECTIONS[data["direction"]], self._map_name(data["map"]), int(data["offset"]))

    def _map_name(self, map_id: str) -> str:
        """The map name for a map id, or the id itself if the map is not in
        the checkout."""
        if self._names is None:
            self._names = self.map_names()
        return self._names.get(map_id, map_id)

    def _read_json(self, *parts: str):
        with open(os.path.join(self.root, *parts), encoding="utf-8") as f:
            return json.load(f)


def tileset_dir(tileset: str) -> str:
    """The directory of a tileset: gTileset_GenericBuilding1 is
    generic_building_1."""
    name = tileset[len("gTileset_"):] if tileset.startswith("gTileset_") else tileset
    return re.sub(r"(?<!^)(?=[A-Z])|(?<=[a-z])(?=\d)", "_", name).lower()


def _npc(index: int, event: Mapping) -> Npc:
    movement = event.get("movement_type", "")
    tile = Tile(event["x"], event["y"])
    sight = 0
    if event.get("trainer_type", "TRAINER_TYPE_NONE") != "TRAINER_TYPE_NONE":
        sight = int(event.get("trainer_sight_or_berry_tree_id", 0))
    flag = event.get("flag", "0")
    return Npc(
        name=event.get("local_id") or "object_%d" % index,
        tile=tile,
        facing=FACING_MOVEMENTS.get(movement),
        sight=sight,
        wander=_wander(tile, movement, event),
        note="%s, %s%s" % (event.get("graphics_id", ""), movement,
                           "" if flag == "0" else ", hidden by " + flag),
    )


def _wander(tile: Tile, movement: str, event: Mapping) -> Optional[Wander]:
    if movement not in WANDER_MOVEMENTS:
        return None
    use_x, use_y = WANDER_MOVEMENTS[movement]
    rx = int(event.get("movement_range_x", 0)) if use_x else 0
    ry = int(event.get("movement_range_y", 0)) if use_y else 0
    return Wander(Tile(tile.x - rx, tile.y - ry), Tile(tile.x + rx, tile.y + ry))


def _sign(index: int, event: Mapping) -> Sign:
    facing_name = event.get("player_facing_dir", "BG_EVENT_PLAYER_FACING_ANY")
    note = event.get("script", "")
    if facing_name.endswith("_ANY"):
        note += " (readable from any side)"
    return Sign("sign_%d" % index, Tile(event["x"], event["y"]), SIGN_FACINGS[facing_name], note)
