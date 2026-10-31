"""What objects on a map mean for walking: trainers' sight, where signs are
read from, which objects block, and the walls that prove where you stand.

The records themselves (Npc, Sign, NamedPoint) are in `maps.schema`; this
module answers questions about them on a grid.

    trainer = Npc("youngster", Tile(3, 4), Direction.NORTH, sight=4)
    sight_tiles(grid, trainer)          # [Tile(3, 3)]: a ledge at (3, 2) ends the line
    reading_tile(sign)                  # the tile in front of the sign
    blocking_tiles(map_file, Blocking.STATIC)   # tiles of NPCs that stand still
"""

import enum
from typing import Dict, List, Set

from pokenav.grid.geometry import CLOCKWISE, Direction, Tile
from pokenav.grid.maps.model import GridMap2D
from pokenav.grid.maps.schema import MapFile, Npc, Sign, Wander
from pokenav.grid.movement import FLAT, ElevationRules, PlayerState, held_at


class Blocking(enum.Enum):
    """Which objects a router treats as blocking."""

    NONE = "none"          #   ignore objects
    STATIC = "static"      #   NPCs that stand still
    ALL = "all"            #   also every tile a wanderer may stand on


def sight_tiles(grid: GridMap2D, npc: Npc, others: Set[Tile] = frozenset()) -> List[Tile]:
    """The tiles a trainer sees: a straight line in front of them, up to
    `npc.sight` tiles, ending before the first blocked cell, off-map tile or
    other object. Empty for an NPC who is not a trainer or faces no way."""
    if npc.sight <= 0 or npc.facing is None:
        return []
    tiles = []
    tile = npc.tile
    for _ in range(npc.sight):
        tile = tile.step(npc.facing)
        cell = grid.at(tile)
        if cell is None or cell.blocked or tile in others:
            break
        tiles.append(tile)
    return tiles


def watched_tiles(map_file: MapFile) -> Dict[Tile, List[str]]:
    """For each tile some trainer sees, the names of the trainers who see it."""
    others = {npc.tile for npc in map_file.npcs}
    watched: Dict[Tile, List[str]] = {}
    for npc in map_file.npcs:
        for tile in sight_tiles(map_file.grid, npc, others - {npc.tile}):
            watched.setdefault(tile, []).append(npc.name)
    return watched


def reading_tile(sign: Sign) -> Tile:
    """The tile to stand on to read `sign`, facing `sign.facing`."""
    return sign.tile.step(sign.facing.opposite)


def can_read(sign: Sign, tile: Tile, facing: Direction) -> bool:
    """Whether pressing A on `tile` while facing `facing` reads `sign`."""
    return tile == reading_tile(sign) and facing is sign.facing


def wander_tiles(wander: Wander) -> List[Tile]:
    """Every tile of a wander patch, row by row."""
    return [Tile(x, y)
            for y in range(wander.low.y, wander.high.y + 1)
            for x in range(wander.low.x, wander.high.x + 1)]


def blocking_tiles(map_file: MapFile, blocking: Blocking) -> Set[Tile]:
    """The tiles a router should treat as holding an object."""
    if blocking is Blocking.NONE:
        return set()
    tiles = {npc.tile for npc in map_file.npcs if npc.wander is None}
    if blocking is Blocking.ALL:
        for npc in map_file.npcs:
            if npc.wander is not None:
                tiles.update(wander_tiles(npc.wander))
                tiles.add(npc.tile)
    return tiles


def walls_around(grid: GridMap2D, tile: Tile, rules: ElevationRules = FLAT,
                 objects: Set[Tile] = frozenset(), elevation: int = 0) -> List[Direction]:
    """The directions in which holding the stick on `tile` keeps the player
    there: the walls a walk can use to prove it stands on `tile`."""
    state = PlayerState(tile, elevation)
    return [d for d in CLOCKWISE if held_at(grid, state, d, rules, objects)]


def is_corner(grid: GridMap2D, tile: Tile, rules: ElevationRules = FLAT,
              objects: Set[Tile] = frozenset(), elevation: int = 0) -> bool:
    """Whether `tile` has walls in two directions at right angles, so two
    walks (one into each) end on it from anywhere in a room: an anchor."""
    walls = walls_around(grid, tile, rules, objects, elevation)
    return any(d.turn() in walls for d in walls)
