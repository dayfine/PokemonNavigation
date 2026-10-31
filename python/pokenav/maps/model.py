"""Cells and a single map: the data every planner reads.

A map is a grid of cells. Each cell holds three facts, the same three the
decompiled GBA games store per tile:

- `blocked`: whether a plain step onto it is refused (collision);
- `elevation`: a level from 0 to 15, compared by the movement rules;
- `behavior`: what the tile does beyond collision, from `Behavior`.

The model knows nothing about how a map is drawn as text or which game it
comes from: the text legend is `maps.textgrid`, the file format
`maps.schema`, and what each elevation means in a game is in `pokenav.games`.

    >>> grid = MapGrid("room", [[Cell(), Cell(behavior=Behavior.TALL_GRASS)]])
    >>> grid.at(Tile(1, 0)).behavior
    <Behavior.TALL_GRASS: 'tall_grass'>
    >>> grid.at(Tile(2, 0)) is None, grid.edge_crossed(Tile(2, 0))
    (True, <Direction.EAST: (1, 0)>)
"""

import enum
from typing import Iterator, List, NamedTuple, Optional, Sequence

from pokenav.geometry import Direction, Tile


class Behavior(enum.Enum):
    """What a tile does besides blocking or not. Values are the names used in
    map files."""

    NONE = "none"
    #   Crossed only in the ledge's direction, with a hop past it.
    LEDGE_NORTH = "ledge_north"
    LEDGE_EAST = "ledge_east"
    LEDGE_SOUTH = "ledge_south"
    LEDGE_WEST = "ledge_west"
    #   Walking into it leaves the map through a warp (a building door).
    DOOR = "door"
    #   Stepping onto it leaves the map through a warp (stairs, a cave exit).
    WARP = "warp"
    #   Needs surfing; blocks a walking player.
    WATER = "water"
    #   Walkable, with wild encounters that interrupt a walk.
    TALL_GRASS = "tall_grass"
    #   Read by facing it and pressing A; blocks like a wall.
    SIGN = "sign"
    #   Blocks; someone behind it can be talked to across it.
    COUNTER = "counter"
    #   The player slides until something stops them.
    ICE = "ice"
    #   The player is moved in a fixed direction once on it.
    FORCED_NORTH = "forced_north"
    FORCED_EAST = "forced_east"
    FORCED_SOUTH = "forced_south"
    FORCED_WEST = "forced_west"
    #   Not mapped: off the edge of the known map, or ground nobody has
    #   checked. It may be an exit, so it is neither a wall nor walkable.
    UNKNOWN = "unknown"


#   The direction a ledge can be crossed in.
LEDGE_DIRECTION = {
    Behavior.LEDGE_NORTH: Direction.NORTH,
    Behavior.LEDGE_EAST: Direction.EAST,
    Behavior.LEDGE_SOUTH: Direction.SOUTH,
    Behavior.LEDGE_WEST: Direction.WEST,
}

#   The direction a forced-move tile pushes the player.
FORCED_DIRECTION = {
    Behavior.FORCED_NORTH: Direction.NORTH,
    Behavior.FORCED_EAST: Direction.EAST,
    Behavior.FORCED_SOUTH: Direction.SOUTH,
    Behavior.FORCED_WEST: Direction.WEST,
}

#   Elevations are stored in four bits in the GBA games' map data, so a cell's
#   elevation is 0 to 15. Games with fewer levels use a subset.
ELEVATION_LEVELS = 16


class Cell(NamedTuple):
    """One tile of a map: collision, elevation and behavior."""

    blocked: bool = False
    elevation: int = 0
    behavior: Behavior = Behavior.NONE


#   An open walkable cell and a wall, the two most common cells.
OPEN = Cell()
WALL = Cell(blocked=True)


class Viewport(NamedTuple):
    """The tiles the game shows around the player: `width` x `height`, with
    the player drawn at column `player_x` and row `player_y` of that window.
    The values are per game (see `pokenav.games`)."""

    width: int
    height: int
    player_x: int
    player_y: int

    def window(self, center: Tile) -> Iterator[Tile]:
        """Every map tile on screen while the player stands on `center`."""
        left = center.x - self.player_x
        top = center.y - self.player_y
        for y in range(top, top + self.height):
            for x in range(left, left + self.width):
                yield Tile(x, y)


class MapGrid:
    """One map: a name, a width and height, and a cell per tile.

    Tiles outside the grid have no cell (`at` returns None); `edge_crossed`
    says which edge they lie past, since leaving a map is a move to another
    map or a wall, which the world decides, not the grid.
    """

    def __init__(self, name: str, rows: Sequence[Sequence[Cell]]):
        """`rows` is a list of rows, top first, all the same length."""
        _check_rows(name, rows)
        self.name = name
        self.height = len(rows)
        self.width = len(rows[0]) if rows else 0
        self._cells: List[Cell] = [cell for row in rows for cell in row]

    @classmethod
    def filled(cls, name: str, width: int, height: int, cell: Cell = OPEN) -> "MapGrid":
        """A `width` x `height` map with every cell the same."""
        return cls(name, [[cell] * width for _ in range(height)])

    def contains(self, tile: Tile) -> bool:
        return 0 <= tile.x < self.width and 0 <= tile.y < self.height

    def at(self, tile: Tile) -> Optional[Cell]:
        """The cell at `tile`, or None if `tile` is off the map."""
        if not self.contains(tile):
            return None
        return self._cells[tile.y * self.width + tile.x]

    def set(self, tile: Tile, cell: Cell) -> None:
        """Replaces one cell, e.g. a wall found on the console."""
        if not self.contains(tile):
            raise IndexError("%s is off map %r" % (tile, self.name))
        self._cells[tile.y * self.width + tile.x] = cell

    def edge_crossed(self, tile: Tile) -> Optional[Direction]:
        """The edge an off-map tile lies past, or None for a tile on the map.
        A tile past a corner reports its vertical edge."""
        if tile.y < 0:
            return Direction.NORTH
        if tile.y >= self.height:
            return Direction.SOUTH
        if tile.x < 0:
            return Direction.WEST
        if tile.x >= self.width:
            return Direction.EAST
        return None

    def tiles(self) -> Iterator[Tile]:
        """Every tile of the map, row by row from the top."""
        for y in range(self.height):
            for x in range(self.width):
                yield Tile(x, y)

    def rows(self) -> List[List[Cell]]:
        """The cells as a list of rows, top first."""
        w = self.width
        return [self._cells[y * w:(y + 1) * w] for y in range(self.height)]

    def find(self, behavior: Behavior) -> List[Tile]:
        """The tiles with `behavior`, row by row."""
        return [t for t in self.tiles() if self.at(t).behavior is behavior]

    def fills(self, viewport: Viewport) -> bool:
        """Whether the map is at least as large as the screen both ways. A map
        that does not fill it (a small room) always shows black around it."""
        return self.width >= viewport.width and self.height >= viewport.height

    def off_map_fraction(self, center: Tile, viewport: Viewport) -> float:
        """The share of the screen, 0 to 1, that shows no tile of this map
        while the player stands on `center`. Ignores connected maps."""
        window = list(viewport.window(center))
        off = sum(1 for tile in window if not self.contains(tile))
        return off / len(window)

    def __eq__(self, other) -> bool:
        if not isinstance(other, MapGrid):
            return NotImplemented
        return (self.name, self.width, self._cells) == (other.name, other.width, other._cells)

    def __repr__(self) -> str:
        return "MapGrid(%r, %dx%d)" % (self.name, self.width, self.height)


def _check_rows(name: str, rows: Sequence[Sequence[Cell]]) -> None:
    """Raises ValueError for ragged rows or an elevation out of range."""
    widths = {len(row) for row in rows}
    if len(widths) > 1:
        raise ValueError("map %r has rows of different widths: %s" % (name, sorted(widths)))
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if not 0 <= cell.elevation < ELEVATION_LEVELS:
                raise ValueError("map %r: elevation %d at (%d, %d) is out of range"
                                 % (name, cell.elevation, x, y))
