"""Pokemon FireRed / LeafGreen: what the core model's numbers mean here.

Source: the pokefirered decompilation. Elevation rules are in
src/event_object_movement.c (IsElevationMismatchAt and
ObjectEventUpdateElevation): elevation 0 is a transition tile that connects
every level, and 15 is a multi-level tile (bridges) that keeps the player's
elevation. The screen is 15 x 10 tiles (VIEWPORT). Behavior numbers are from
include/constants/metatile_behaviors.h.

The command line that imports maps from a pokefirered checkout is
`pokenav.cli.import_frlg`.
"""

from pokenav.grid.maps.model import Behavior, Viewport
from pokenav.grid.maps.pret import Checkout, PretGame
from pokenav.grid.movement import ElevationRules
from pokenav.physics.model import TileError

#   A transition tile: steps onto or off it ignore elevation.
TRANSITION_ELEVATION = 0
#   A multi-level tile: the player keeps the elevation they arrived with.
MULTI_LEVEL_ELEVATION = 15

ELEVATION_RULES = ElevationRules(
    any_level=frozenset({TRANSITION_ELEVATION}),
    keep_level=frozenset({MULTI_LEVEL_ELEVATION}),
)

#   The GBA screen is 240 x 160 pixels, 15 x 10 tiles of 16 pixels. The
#   player is drawn in column 7 (the middle) and row 4 (of rows 0 to 9); the
#   row is from the screen layout and not yet checked on the console.
VIEWPORT = Viewport(width=15, height=10, player_x=7, player_y=4)

#   FRLG moves whole tiles, 16 frames a step, so a walker that counts steps
#   (taps, or a hold timed in steps) ends where it meant to: open legs are
#   exact.
OPEN_LEG_ERROR = TileError()

#   The primary tileset holds metatiles 0 to 639 (NUM_METATILES_IN_PRIMARY
#   in include/fieldmap.h); the secondary tileset's start after it.
PRIMARY_METATILES = 640


def _same(behavior: Behavior, *numbers: int):
    return {number: behavior for number in numbers}


#   Metatile behavior numbers and what they mean for walking. Numbers not
#   listed (sand, puddles, furniture that only blocks by collision) are
#   Behavior.NONE.
BEHAVIORS = {
    0x02: Behavior.TALL_GRASS,                  # MB_TALL_GRASS
    0x23: Behavior.ICE,                         # MB_ICE
    0x38: Behavior.LEDGE_EAST,                  # MB_JUMP_EAST
    0x39: Behavior.LEDGE_WEST,                  # MB_JUMP_WEST
    0x3A: Behavior.LEDGE_NORTH,                 # MB_JUMP_NORTH
    0x3B: Behavior.LEDGE_SOUTH,                 # MB_JUMP_SOUTH
    0x40: Behavior.FORCED_EAST,                 # MB_WALK_EAST
    0x41: Behavior.FORCED_WEST,                 # MB_WALK_WEST
    0x42: Behavior.FORCED_NORTH,                # MB_WALK_NORTH
    0x43: Behavior.FORCED_SOUTH,                # MB_WALK_SOUTH
    0x44: Behavior.FORCED_EAST,                 # MB_SLIDE_EAST
    0x45: Behavior.FORCED_WEST,                 # MB_SLIDE_WEST
    0x46: Behavior.FORCED_NORTH,                # MB_SLIDE_NORTH
    0x47: Behavior.FORCED_SOUTH,                # MB_SLIDE_SOUTH
    0x60: Behavior.DOOR,                        # MB_CAVE_DOOR
    0x69: Behavior.DOOR,                        # MB_WARP_DOOR
    0x80: Behavior.COUNTER,                     # MB_COUNTER
}
#   Pond, fast, deep and ocean water, the waterfall, the currents, and
#   Cycling Road water.
BEHAVIORS.update(_same(Behavior.WATER, 0x10, 0x11, 0x12, 0x13, 0x15, 0x1B, 0x50, 0x51, 0x52, 0x53))
#   Ladder, arrow warps (door mats), fall, regular and stair warps. Arrow
#   warps really fire when the player presses their direction while on them;
#   the model treats them as firing on the step onto them.
BEHAVIORS.update(_same(Behavior.WARP, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x6C, 0x6D, 0x6E, 0x6F))
#   Signposts, the Pokemon Center and Mart signs, the Indigo Plateau signs.
BEHAVIORS.update(_same(Behavior.SIGN, 0x84, 0x87, 0x88, 0x91, 0x92))

PRET = PretGame(primary_metatiles=PRIMARY_METATILES, behaviors=BEHAVIORS)

