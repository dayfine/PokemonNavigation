"""Step rules on a flat 2D tile map (`GridMap2D`): what one press of a
direction does on one map. Maps with floors stacked in one grid (3D games)
would need their own rules.

`step` takes where the player stands (a tile and their current elevation) and
a direction, and returns one of:

- `Moved(state)`: the player walked one tile, or slid further on ice or a
  forced-move tile;
- `Hop(state)`: the player hopped a ledge, two tiles;
- `Blocked(reason)`: the player stayed put;
- `Warp(tile)`: the player walked into a door or onto a warp tile at `tile`;
- `Edge(direction)`: the step leaves the map (the world decides what is past
  it).

`held_at` says whether holding the direction keeps the player in place, the
way a wall does. A door, a map edge, unknown ground and an NPC do not: the
first three lead somewhere, and an NPC may walk away. A planner can end a leg
"to the wall" only where `held_at` is true.

Elevation follows the rules of the GBA games' maps, as data in
`ElevationRules`: a step between different elevations is refused unless the
player or the tile is on an "any level" elevation (a transition tile), and a
"keep level" tile (a bridge) leaves the player's elevation as it was. What
the numbers are in each game is in `pokenav.games`.

    >>> from pokenav.grid.maps.textgrid import parse
    >>> grid = parse("#.#\\n#v#\\n#.#\\n").grid
    >>> step(grid, PlayerState(Tile(1, 0)), Direction.SOUTH)
    Hop(state=PlayerState(tile=Tile(x=1, y=2), elevation=0))
    >>> step(grid, PlayerState(Tile(1, 2)), Direction.NORTH)
    Blocked(reason=<BlockReason.LEDGE: 'ledge'>)
"""

import enum
from typing import AbstractSet, FrozenSet, NamedTuple, Optional, Union

from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.model import FORCED_DIRECTION, LEDGE_DIRECTION, Behavior, Cell, GridMap2D


class PlayerState(NamedTuple):
    """Where the player is: a tile, and the elevation they move at."""

    tile: Tile
    elevation: int = 0


class ElevationRules(NamedTuple):
    """Which elevations are special. `any_level` elevations connect to every
    other (transition tiles); `keep_level` tiles keep the player's elevation
    (bridges, which can be walked over and under). The default has neither:
    every step must stay on one elevation."""

    any_level: FrozenSet[int] = frozenset()
    keep_level: FrozenSet[int] = frozenset()


FLAT = ElevationRules()


class BlockReason(enum.Enum):
    """Why a step was refused."""

    WALL = "wall"            #   a blocked cell: wall, sign, counter, water
    LEDGE = "ledge"          #   a ledge from the wrong side, or no room to land
    ELEVATION = "elevation"  #   a different elevation without a transition
    OBJECT = "object"        #   an NPC or other object on the tile
    UNKNOWN = "unknown"      #   a cell nobody has mapped


#   The reasons that hold the player in place while the direction is held.
HOLDING_REASONS = frozenset({BlockReason.WALL, BlockReason.LEDGE, BlockReason.ELEVATION})


class Moved(NamedTuple):
    state: PlayerState


class Hop(NamedTuple):
    state: PlayerState


class Blocked(NamedTuple):
    reason: BlockReason


class Warp(NamedTuple):
    tile: Tile


class Edge(NamedTuple):
    direction: Direction


StepResult = Union[Moved, Hop, Blocked, Warp, Edge]

#   Tiles that hold an object, which blocks a step but does not hold the
#   player in place.
Objects = AbstractSet[Tile]

#   A ledge hop moves this many tiles: over the ledge and onto the tile past it.
LEDGE_HOP_TILES = 2


def step(grid: GridMap2D, state: PlayerState, direction: Direction,
         rules: ElevationRules = FLAT, objects: Objects = frozenset()) -> StepResult:
    """What pressing `direction` once does from `state`."""
    result = _single_step(grid, state, direction, rules, objects)
    if isinstance(result, Moved):
        return _slide(grid, result.state, direction, rules, objects)
    return result


def held_at(grid: GridMap2D, state: PlayerState, direction: Direction,
            rules: ElevationRules = FLAT, objects: Objects = frozenset()) -> bool:
    """Whether holding `direction` keeps the player at `state`."""
    result = step(grid, state, direction, rules, objects)
    return isinstance(result, Blocked) and result.reason in HOLDING_REASONS


class Walk(NamedTuple):
    """The end of a walk in one direction: where the player is, the tiles
    covered (a ledge hop counts 2), and the step result that ended it, or
    None if it ended because `max_tiles` was reached."""

    state: PlayerState
    tiles: int
    stop: Optional[StepResult]

    @property
    def held(self) -> bool:
        """Whether the walk ended held in place, as against a wall."""
        return isinstance(self.stop, Blocked) and self.stop.reason in HOLDING_REASONS


def walk(grid: GridMap2D, state: PlayerState, direction: Direction,
         rules: ElevationRules = FLAT, objects: Objects = frozenset(),
         max_tiles: Optional[int] = None) -> Walk:
    """Holds `direction` from `state` until a step fails, or until at least
    `max_tiles` tiles are covered."""
    tiles = 0
    while max_tiles is None or tiles < max_tiles:
        result = step(grid, state, direction, rules, objects)
        if not isinstance(result, (Moved, Hop)):
            return Walk(state, tiles, result)
        tiles += tiles_moved(result, state.tile)
        state = result.state
    return Walk(state, tiles, None)


def tiles_moved(result: StepResult, start: Tile) -> int:
    """How many tiles a step result moved from `start`: 0 unless it moved or
    hopped."""
    if isinstance(result, (Moved, Hop)):
        return start.manhattan(result.state.tile)
    return 0


def _single_step(grid: GridMap2D, state: PlayerState, direction: Direction,
                 rules: ElevationRules, objects: Objects) -> StepResult:
    """One step without sliding."""
    target = state.tile.step(direction)
    cell = grid.at(target)
    if cell is None:
        return Edge(direction)
    if target in objects:
        return Blocked(BlockReason.OBJECT)
    if cell.behavior in LEDGE_DIRECTION:
        return _ledge(grid, state, direction, cell, rules, objects)
    if cell.behavior is Behavior.DOOR:
        return Warp(target)
    if cell.behavior is Behavior.UNKNOWN:
        return Blocked(BlockReason.UNKNOWN)
    return _enter(state, target, cell, rules)


def _enter(state: PlayerState, target: Tile, cell: Cell, rules: ElevationRules) -> StepResult:
    """A plain step onto `target`, whose cell is `cell`."""
    if cell.blocked:
        return Blocked(BlockReason.WALL)
    if not _elevation_allows(state.elevation, cell.elevation, rules):
        return Blocked(BlockReason.ELEVATION)
    if cell.behavior is Behavior.WARP:
        return Warp(target)
    return Moved(PlayerState(target, _elevation_after(state.elevation, cell.elevation, rules)))


def _ledge(grid: GridMap2D, state: PlayerState, direction: Direction, cell: Cell,
           rules: ElevationRules, objects: Objects) -> StepResult:
    """A step into a ledge: a hop if it is crossed in its direction and the
    tile past it can be stood on."""
    if LEDGE_DIRECTION[cell.behavior] is not direction:
        return Blocked(BlockReason.LEDGE)
    landing = state.tile.step(direction, LEDGE_HOP_TILES)
    landing_cell = grid.at(landing)
    if landing_cell is None or landing_cell.blocked or landing in objects:
        return Blocked(BlockReason.LEDGE)
    return Hop(PlayerState(landing, _elevation_after(state.elevation, landing_cell.elevation, rules)))


def _slide(grid: GridMap2D, state: PlayerState, direction: Direction,
           rules: ElevationRules, objects: Objects) -> Moved:
    """Moves on from `state` while it is on ice (onward in `direction`) or a
    forced-move tile (in that tile's direction), until a step fails."""
    seen = {state}
    while True:
        push = _push_direction(grid.at(state.tile), direction)
        if push is None:
            return Moved(state)
        result = _single_step(grid, state, push, rules, objects)
        if not isinstance(result, Moved) or result.state in seen:
            return Moved(state)
        state, direction = result.state, push
        seen.add(state)


def _push_direction(cell: Cell, direction: Direction) -> Optional[Direction]:
    if cell.behavior is Behavior.ICE:
        return direction
    return FORCED_DIRECTION.get(cell.behavior)


def _elevation_allows(current: int, target: int, rules: ElevationRules) -> bool:
    if current in rules.any_level:
        return True
    if target in rules.any_level or target in rules.keep_level:
        return True
    return current == target


def _elevation_after(current: int, target: int, rules: ElevationRules) -> int:
    return current if target in rules.keep_level else target
