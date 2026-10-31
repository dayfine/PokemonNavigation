"""Error models: how far a counted leg may miss.

A counted leg (a stick hold timed for n tiles, or n D-pad taps) may end some
tiles from where it was meant to; a clip to a wall is exact. `TileError`
holds one way of walking's numbers. The per-game values come from console
measurements (games/<game>/MEASUREMENTS.md); the parameter files that hold
them, and the model of a whole game, come with the leg kinds.

    TileError(per_tile=0.15).spread(14)    # 1: a 14-tile stick hold may miss a tile
    TileError().spread(20)                 # 0: exact, as D-pad taps are on BDSP
"""

import math
from typing import NamedTuple

#   The player starts a leg on a tile's centre, so a leg that misses by less
#   than this still ends on the planned tile.
HALF_TILE = 0.5


class TileError(NamedTuple):
    """How far a counted leg of n tiles may end from n: up to `per_tile` *
    sqrt(n) + `overshoot` tiles either way. Per-step errors add up like a
    random walk (BDSP: 0.15 a step came to about half a tile over 18 steps),
    hence the square root; `overshoot` is a fixed slide after letting go.
    `spread` rounds to whole tiles."""

    per_tile: float = 0.0
    overshoot: float = 0.0

    def spread(self, tiles: int) -> int:
        """The tiles a leg of `tiles` tiles may end either side of its end."""
        error = self.per_tile * math.sqrt(tiles) + self.overshoot
        return int(math.floor(error + HALF_TILE))
