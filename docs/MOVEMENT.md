# Movement rules

What one press of a direction does on one map (`pokenav.grid.movement`).

| Target tile | Result | Holds the player? |
|---|---|---|
| open ground, tall grass | `Moved` one tile | - |
| ice, forced-move tile | `Moved`, sliding on until a step fails | - |
| wall, sign, counter, water | `Blocked(WALL)` | yes |
| ledge, crossed in its direction | `Hop` two tiles, if the landing tile is open | - |
| ledge, any other direction | `Blocked(LEDGE)` | yes |
| another elevation, no transition | `Blocked(ELEVATION)` | yes |
| an object (NPC) | `Blocked(OBJECT)` | no: it may walk away |
| unknown ground | `Blocked(UNKNOWN)` | no: it may be an exit |
| door | `Warp` (walking into it) | no |
| warp tile | `Warp` (stepping onto it) | no |
| off the map | `Edge(direction)` | no: the world decides |

"Holds" is `held_at`: holding the stick keeps the player on the tile, so a
leg can be walked "to the wall" and end on a known tile however long it is
held. `walk` holds one direction until a step fails and reports the tiles
covered (a ledge hop counts 2) and what stopped it.

## Elevation

`ElevationRules` lists two kinds of special elevation:

- **any level** (transition tiles): a player on one, or a step onto one, may
  change level;
- **keep level** (bridges): the player keeps the elevation they had, so the
  same tile can be crossed over (on the bridge's level) or under.

Otherwise a step between different elevations is refused. With no rules
(`FLAT`) every step stays on one elevation. FireRed / LeafGreen use 0 for
transitions and 15 for multi-level tiles (`pokenav.games.frlg`).
