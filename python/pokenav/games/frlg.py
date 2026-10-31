"""Pokemon FireRed / LeafGreen: what the core model's numbers mean here.

Source: the pokefirered decompilation. Elevation rules are in
src/event_object_movement.c (IsElevationMismatchAt and
ObjectEventUpdateElevation): elevation 0 is a transition tile that connects
every level, and 15 is a multi-level tile (bridges) that keeps the player's
elevation. The screen is 15 x 10 tiles (VIEWPORT).
"""

from pokenav.maps.model import Viewport
from pokenav.movement import ElevationRules

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
