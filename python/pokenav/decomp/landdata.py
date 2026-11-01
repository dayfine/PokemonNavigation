"""Land data of the DS Sinnoh games (pret/pokediamond, pret/pokeplatinum):
the tile attributes of a 32 x 32 map cell, the map matrix that places cells
in the world, and what each tile behavior means for walking.

A land data file (Platinum res/field/maps/data/map_data_NNN.bin, Diamond
files/fielddata/land_data/land_data_release/narc_NNNN.bin) starts with a
16-byte header of four little-endian u32 sizes (tile attributes, always
2048; map props; 3D model; height data), then 1024 little-endian u16
attributes, row-major, index z * 32 + x. Bit 0x8000 is collision and the
low byte the behavior (pokeplatinum
include/constants/field/map_tile_behaviors.h). Both games use the same
layout; Diamond's and Platinum's files for the same place are identical
except where the games differ. Heights live in the BDHC blob, not per tile,
so cells here have elevation 0.

A map matrix (Platinum res/field/matrices/map_matrix_NNN.json, Diamond
files/fielddata/mapmatrix/map_matrix/narc_NNNN.bin) is a grid of cells,
each a land data number and the map header that owns it. World tile
(x, z) is in cell (row z // 32, column x // 32) at (x % 32, z % 32).

    attrs = attributes(open("map_data_005.bin", "rb").read())
    cell(attrs[10 * 32 + 44])          # Cell(behavior=Behavior.TALL_GRASS)
    matrix = matrix_from_json(json.load(open("map_matrix_000.json")))
    matrix.maps[26][3], matrix.headers[26][3]   # (5, 'MAP_HEADER_ROUTE_201')
"""

import struct
from typing import Dict, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from pokenav.grid.maps.model import Behavior, Cell

#   Every cell is 32 x 32 tiles.
CELL_SIZE = 32
TILES_PER_CELL = CELL_SIZE * CELL_SIZE
#   The file: four u32 sizes, then one u16 per tile.
HEADER_SIZE = 16
ATTRIBUTES_BYTES = 2 * TILES_PER_CELL

#   Attribute bits.
BLOCKED = 0x8000
BEHAVIOR_MASK = 0xFF

#   Behavior numbers (TILE_BEHAVIOR_* in pokeplatinum
#   include/constants/field/map_tile_behaviors.h) that the walk model needs.
TALL_GRASS = 0x02
VERY_TALL_GRASS = 0x03
CAVE_FLOOR = 0x08
MOUNTAIN_FLOOR = 0x0C
WATER_RIVER = 0x10
WATERFALL = 0x13
WATER_SEA = 0x15
ICE = 0x20
SAND = 0x21
#   One-way blocks: BLOCK_EASTWARD .. BLOCK_SOUTH_AND_WEST, then
#   BLOCK_NORTH_AND_SOUTH and BLOCK_EAST_AND_WEST. The model has no cell
#   kind for them; the generator counts them in a note.
ONE_WAY_BLOCKS = frozenset(range(0x30, 0x38)) | frozenset({0x49, 0x4A})
#   Bridges of every kind: plain ground to a walker.
BRIDGES = frozenset(range(0x70, 0x7E))
#   Walked-into tiles: cave mouths (WARP_ENTRANCE_EAST .. SOUTH) and doors.
WARP_ENTRANCES = (0x62, 0x63, 0x64, 0x65)
DOOR = 0x69
#   Stood-on warp tiles: stairs, the warp panel, and WARP_EAST .. SOUTH
#   (cave exits, map-edge gates, doorways you step into).
WARP_STAIRS = (0x5E, 0x5F)
WARP_PANEL = 0x67
WARP_TILES = (0x6C, 0x6D, 0x6E, 0x6F)


def _same(behavior: Behavior, *numbers: int) -> Dict[int, Behavior]:
    return {number: behavior for number in numbers}


#   Behavior number to cell behavior. Numbers not listed (plain ground, cave
#   and mountain floors, sand, puddles, one-way blocks, bridges, furniture)
#   are Behavior.NONE.
BEHAVIORS: Dict[int, Behavior] = {
    TALL_GRASS: Behavior.TALL_GRASS,
    VERY_TALL_GRASS: Behavior.TALL_GRASS,
    ICE: Behavior.ICE,
    0x38: Behavior.LEDGE_EAST,                  # JUMP_EAST
    0x39: Behavior.LEDGE_WEST,                  # JUMP_WEST
    0x3A: Behavior.LEDGE_NORTH,                 # JUMP_NORTH
    0x3B: Behavior.LEDGE_SOUTH,                 # JUMP_SOUTH
    0x40: Behavior.FORCED_EAST,                 # SLIDE_EASTWARD
    0x41: Behavior.FORCED_WEST,                 # SLIDE_WESTWARD
    0x42: Behavior.FORCED_NORTH,                # SLIDE_NORTHWARD
    0x43: Behavior.FORCED_SOUTH,                # SLIDE_SOUTHWARD
    #   JUMP_*_TWICE: a two-tile hop. The model knows one-tile ledges; the
    #   generator notes where these are.
    0x5A: Behavior.LEDGE_NORTH,
    0x5B: Behavior.LEDGE_SOUTH,
    0x5C: Behavior.LEDGE_WEST,
    0x5D: Behavior.LEDGE_EAST,
    DOOR: Behavior.DOOR,
}
BEHAVIORS.update(_same(Behavior.WATER, WATER_RIVER, WATERFALL, WATER_SEA))
BEHAVIORS.update(_same(Behavior.DOOR, *WARP_ENTRANCES))
BEHAVIORS.update(_same(Behavior.WARP, WARP_PANEL, *WARP_STAIRS, *WARP_TILES))
DOUBLE_JUMPS = frozenset({0x5A, 0x5B, 0x5C, 0x5D})

#   Cell kinds whose collision does not depend on the attribute's bit: water
#   and ledges and doors are walls to a plain step; a warp tile is stood on.
ALWAYS_BLOCKED = frozenset({Behavior.WATER, Behavior.DOOR, Behavior.LEDGE_NORTH, Behavior.LEDGE_EAST,
                            Behavior.LEDGE_SOUTH, Behavior.LEDGE_WEST})
NEVER_BLOCKED = frozenset({Behavior.WARP})

#   A tile no loaded cell covers.
UNKNOWN_CELL = Cell(blocked=True, behavior=Behavior.UNKNOWN)


def attributes(data: bytes) -> Tuple[int, ...]:
    """The 1024 tile attributes of a land data file. Raises ValueError if
    the header does not announce 2048 bytes of them or the file is short."""
    if len(data) < HEADER_SIZE + ATTRIBUTES_BYTES:
        raise ValueError("land data has %d bytes, fewer than a header and 1024 tiles" % len(data))
    sizes = struct.unpack_from("<4I", data, 0)
    if sizes[0] != ATTRIBUTES_BYTES:
        raise ValueError("land data header says %d bytes of tile attributes, not %d"
                         % (sizes[0], ATTRIBUTES_BYTES))
    return struct.unpack_from("<%dH" % TILES_PER_CELL, data, HEADER_SIZE)


def behavior_number(attribute: int) -> int:
    return attribute & BEHAVIOR_MASK


def cell(attribute: int) -> Cell:
    """The cell a tile attribute stands for."""
    behavior = BEHAVIORS.get(behavior_number(attribute), Behavior.NONE)
    blocked = bool(attribute & BLOCKED)
    if behavior in ALWAYS_BLOCKED:
        blocked = True
    elif behavior in NEVER_BLOCKED:
        blocked = False
    return Cell(blocked=blocked, behavior=behavior)


def is_cave_floor(attribute: int) -> bool:
    """Whether wild battles start on the tile as in a cave: on every step."""
    return behavior_number(attribute) == CAVE_FLOOR


class Matrix(NamedTuple):
    """A map matrix: the land data number of each cell (None where the
    matrix has no cell) and the header constant that owns it (None if the
    matrix has no header table). `maps[row][col]`."""

    name: str
    maps: List[List[Optional[int]]]
    headers: List[List[Optional[str]]]

    @property
    def height(self) -> int:
        return len(self.maps)

    @property
    def width(self) -> int:
        return len(self.maps[0]) if self.maps else 0

    def header_at(self, row: int, col: int) -> Optional[str]:
        """The header owning cell (row, col), or None outside the matrix or
        where the cell has none."""
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.headers[row][col]
        return None

    def cells_of(self, header: str) -> List[Tuple[int, int]]:
        """The (row, col) cells a header owns."""
        return [(r, c) for r in range(self.height) for c in range(self.width) if self.headers[r][c] == header]

    def origin_of(self, header: str) -> Optional[Tuple[int, int]]:
        """The world (x, z) of the top-left corner of the box holding a
        header's cells; None if it owns none."""
        cells = self.cells_of(header)
        if not cells:
            return None
        return (CELL_SIZE * min(c for _, c in cells), CELL_SIZE * min(r for r, _ in cells))


def matrix_from_json(data: Mapping) -> Matrix:
    """Platinum's matrix: {"name", "maps": [["MAP_005", "MAP_NONE", ...]],
    "headers": [["MAP_HEADER_ROUTE_201", ...]] or []}."""
    maps = [[_map_number(entry) for entry in row] for row in data["maps"]]
    headers = data.get("headers") or []
    if not headers:
        headers = [[None] * len(row) for row in maps]
    return Matrix(data.get("name", ""), maps, [list(row) for row in headers])


def _map_number(entry: str) -> Optional[int]:
    if entry == "MAP_NONE":
        return None
    return int(entry[len("MAP_"):])


#   Diamond's binary matrix: width, height, has-headers, has-altitudes and
#   the name's length as u8, the name, then the header ids (u16 each), the
#   altitudes (u8 each) and the land data numbers (u16 each), row-major.
#   0xFFFF is an empty cell. (pokediamond include/map_matrix.h)
NO_CELL = 0xFFFF


def matrix_from_binary(data: bytes, header_names: Mapping[int, str]) -> Matrix:
    """Diamond's matrix; `header_names` turns header ids into constants
    (pokediamond include/constants/maps.h)."""
    width, height, has_headers, has_altitudes, name_length = struct.unpack_from("<5B", data, 0)
    offset = 5
    name = data[offset:offset + name_length].decode("ascii")
    offset += name_length
    count = width * height
    headers: List[List[Optional[str]]] = [[None] * width for _ in range(height)]
    if has_headers:
        ids = struct.unpack_from("<%dH" % count, data, offset)
        offset += 2 * count
        headers = [[header_names.get(ids[r * width + c], "MAP_%d" % ids[r * width + c]) for c in range(width)]
                   for r in range(height)]
    if has_altitudes:
        offset += count
    numbers = struct.unpack_from("<%dH" % count, data, offset)
    maps = [[None if numbers[r * width + c] == NO_CELL else numbers[r * width + c] for c in range(width)]
            for r in range(height)]
    return Matrix(name, maps, headers)


class LandGrid:
    """The loaded cells of one matrix, looked up by world tile."""

    def __init__(self) -> None:
        self._cells: Dict[Tuple[int, int], Sequence[int]] = {}

    def add(self, row: int, col: int, attrs: Sequence[int]) -> None:
        if len(attrs) != TILES_PER_CELL:
            raise ValueError("cell (%d, %d) has %d tiles, not %d" % (row, col, len(attrs), TILES_PER_CELL))
        self._cells[(row, col)] = attrs

    def cells(self) -> List[Tuple[int, int]]:
        return sorted(self._cells)

    def attribute(self, x: int, z: int) -> Optional[int]:
        """The attribute of world tile (x, z), or None if its cell is not
        loaded."""
        if x < 0 or z < 0:
            return None
        attrs = self._cells.get((z // CELL_SIZE, x // CELL_SIZE))
        if attrs is None:
            return None
        return attrs[(z % CELL_SIZE) * CELL_SIZE + (x % CELL_SIZE)]

    def bounds(self) -> Tuple[int, int, int, int]:
        """The world box (x0, z0, width, height) holding every loaded cell."""
        if not self._cells:
            raise ValueError("no cells loaded")
        rows = [r for r, _ in self._cells]
        cols = [c for _, c in self._cells]
        return (CELL_SIZE * min(cols), CELL_SIZE * min(rows),
                CELL_SIZE * (max(cols) - min(cols) + 1), CELL_SIZE * (max(rows) - min(rows) + 1))
