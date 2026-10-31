"""Error models: how far each way of walking may miss, per game and mode.

A game walks on foot and, once the player has one, on a bike (`Mode`). In
each mode a counted leg (D-pad taps or a timed stick hold) may end some
tiles from where it was meant to (`TileError`); a clip to a wall is exact in
every mode. `ExecutionModel` holds one game's numbers, read from its
`games/<game>/physics.txt` by `from_params`.

    model = from_params(params.load("games/bdsp/physics.txt"))
    model.foot.stick.spread(20)      # 1: a 20-tile stick hold may miss a tile
    model.foot.dpad.spread(20)       # 0: 20 D-pad taps land exactly
"""

import enum
import math
from typing import NamedTuple, Optional

from pokenav.physics.params import Params

#   The player starts a leg on a tile's centre, so a leg that misses by less
#   than this still ends on the planned tile.
HALF_TILE = 0.5


class Mode(enum.Enum):
    """How the player moves."""

    FOOT = "foot"
    BIKE = "bike"


class TileError(NamedTuple):
    """How far a counted leg of n tiles may end from n: up to `per_tile` *
    sqrt(n) + `overshoot` tiles either way. Per-step errors add up like a
    random walk (BDSP: 0.15 a step came to about half a tile over 18 steps),
    hence the square root; `overshoot` is a fixed slide after letting go.
    `spread` rounds to whole tiles.

    `lateral` is how many rows the leg may drift sideways: 0 keeps its row
    (D-pad taps; FRLG's grid-locked steps), 1 means a stick hold can slide
    into the next row and catch on a corner there (BDSP, Route 203's sand
    rows and stairs). The planner allows such a leg only where the rows
    beside it are all wall or all open along its length."""

    per_tile: float = 0.0
    overshoot: float = 0.0
    lateral: float = 0.0

    def spread(self, tiles: int) -> int:
        """The tiles a leg of `tiles` tiles may end either side of its end."""
        error = self.per_tile * math.sqrt(tiles) + self.overshoot
        return int(math.floor(error + HALF_TILE))


class ModeModel(NamedTuple):
    """One mode's numbers. `tile_cost` is the time of a tile against
    walking's; `dpad` is None where taps are not used to count tiles. Any
    error with a `spread(tiles)` method will do."""

    tile_cost: float
    dpad: Optional[TileError]
    stick: TileError


class ExecutionModel(NamedTuple):
    """A game's ways of walking. `bike` is None in a game without one. Costs
    are in tiles walked: `turn_tap` for a tap that only turns the player,
    `mount` to get on or off the bike, `door` to wait out a door's fade."""

    #   TODO: tune `door` and `mount`. The game files' values are heuristics:
    #   BDSP's door until ms per walking tile converts its measured fade to
    #   tiles, FRLG's door and mount until their frames are measured.

    foot: ModeModel
    bike: Optional[ModeModel] = None
    turn_tap: float = 0.0
    mount: float = 0.0
    door: float = 0.0

    def mode(self, mode: Mode) -> Optional[ModeModel]:
        return self.foot if mode is Mode.FOOT else self.bike


#   The parameter names `from_params` reads; `bike.*` are optional.
MODE_NAMES = ("tile_cost", "dpad.per_tile", "dpad.overshoot", "dpad.lateral",
              "stick.per_tile", "stick.overshoot", "stick.lateral")
COST_NAMES = ("turn_tap", "mount", "door")


def from_params(params: Params) -> ExecutionModel:
    """The model in a parameter file. Raises ValueError for an unknown or
    missing name."""
    known = {"%s.%s" % (mode.value, name) for mode in Mode for name in MODE_NAMES} | set(COST_NAMES)
    unknown = sorted(set(params) - known)
    if unknown:
        raise ValueError("unknown physics parameters: %s" % ", ".join(unknown))
    has_bike = any(name.startswith(Mode.BIKE.value + ".") for name in params)
    return ExecutionModel(
        foot=_mode_model(params, Mode.FOOT),
        bike=_mode_model(params, Mode.BIKE) if has_bike else None,
        **{name: _value(params, name) for name in COST_NAMES})


def _mode_model(params: Params, mode: Mode) -> ModeModel:
    value = lambda name: _value(params, "%s.%s" % (mode.value, name))
    return ModeModel(
        tile_cost=value("tile_cost"),
        dpad=TileError(value("dpad.per_tile"), value("dpad.overshoot"), value("dpad.lateral")),
        stick=TileError(value("stick.per_tile"), value("stick.overshoot"), value("stick.lateral")),
    )


def _value(params: Params, name: str) -> float:
    if name not in params:
        raise ValueError("missing physics parameter: %s" % name)
    return params[name].value
