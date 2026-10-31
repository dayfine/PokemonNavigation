"""Directions and tiles on a 2D tile map.

Coordinates follow the decompilations and the map files: a tile is (x, y)
with x growing east and y growing south, so row 0 is the top of a map. Every
other module works in these coordinates; a controller's stick convention
(where +1 is often north) belongs to the input layer, not here.

    >>> Tile(3, 4).step(Direction.NORTH)
    Tile(x=3, y=3)
    >>> Direction.parse("w").opposite
    <Direction.EAST: (1, 0)>
    >>> Tile(0, 0).direction_to(Tile(0, 5))
    <Direction.SOUTH: (0, 1)>
"""

import enum
from typing import NamedTuple, Optional


class Direction(enum.Enum):
    """One of the four directions the player can face or move in.

    The value of each member is its (dx, dy) offset for one step.
    """

    NORTH = (0, -1)
    EAST = (1, 0)
    SOUTH = (0, 1)
    WEST = (-1, 0)

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]

    @property
    def opposite(self) -> "Direction":
        return _OPPOSITE[self]

    def turn(self, clockwise: bool = True) -> "Direction":
        """The direction a quarter turn away: east is clockwise from north."""
        step = 1 if clockwise else -1
        index = CLOCKWISE.index(self)
        return CLOCKWISE[(index + step) % len(CLOCKWISE)]

    @property
    def is_vertical(self) -> bool:
        return self.dx == 0

    @classmethod
    def parse(cls, text: str) -> "Direction":
        """A direction from its name or initial, in any case: "north", "N".

        Raises ValueError for anything else.
        """
        key = text.strip().lower()
        try:
            return _BY_NAME[key]
        except KeyError:
            raise ValueError("not a direction: %r" % text) from None


#   The four directions in clockwise order, starting north.
CLOCKWISE = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

_OPPOSITE = {d: CLOCKWISE[(i + 2) % 4] for i, d in enumerate(CLOCKWISE)}

#   Accepted spellings: the full name and the initial, lower case.
_BY_NAME = {}
for _d in Direction:
    _BY_NAME[_d.name.lower()] = _d
    _BY_NAME[_d.name[0].lower()] = _d


class Tile(NamedTuple):
    """A tile position on one map, (x, y) with x east and y south."""

    x: int
    y: int

    def step(self, direction: Direction, count: int = 1) -> "Tile":
        """The tile `count` steps away in `direction`."""
        return Tile(self.x + direction.dx * count, self.y + direction.dy * count)

    def manhattan(self, other: "Tile") -> int:
        """Steps between the two tiles moving only in the four directions."""
        return abs(self.x - other.x) + abs(self.y - other.y)

    def direction_to(self, other: "Tile") -> Optional[Direction]:
        """The direction of a straight line to `other`, or None if `other`
        is this tile or not in line with it."""
        dx = other.x - self.x
        dy = other.y - self.y
        if (dx == 0) == (dy == 0):
            return None
        return Direction((_sign(dx), _sign(dy)))

    def __str__(self) -> str:
        return "(%d, %d)" % (self.x, self.y)


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)
