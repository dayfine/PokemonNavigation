# Map data

How a map is held in `pokenav.grid.maps`. Code: `python/pokenav/grid/maps/`.

## Cells (`maps.model`)

A map is a grid of cells, row 0 at the top, x east and y south. Each cell has:

| Field | Values | Meaning |
|---|---|---|
| `blocked` | true / false | a plain step onto it is refused |
| `elevation` | 0 to 15 | compared by the movement rules; what each level means is per game |
| `behavior` | `Behavior` | what the tile does besides blocking |

Behaviors: `none`, `ledge_north|east|south|west` (crossed one way, with a
hop), `door` (walk into it to warp), `warp` (step onto it to warp), `water`,
`tall_grass`, `sign`, `counter`, `rock` (a wall Rock Smash clears), `ice`,
`forced_north|east|south|west`, and `unknown` (not mapped; may be an exit,
so neither a wall nor walkable).

A tile off the grid has no cell; the map says which edge it lies past, and the
world (maps joined by connections) decides what is there.

### Screen coverage

A `Viewport` is the window of tiles the game draws around the player:
`viewport.window(tile)` lists the tiles on screen while standing on `tile`.
A map smaller than the viewport (a 6 x 6 house on a 15 x 10 screen) always
shows black around it, which screen checks such as battle detection must
allow for.

## Map files (`maps.schema`)

A map's source of truth is a JSON file: rows of characters with the legend
that decodes them, an optional elevation layer (one hex digit per tile), and
named records for what is on the map:

| Key | Holds |
|---|---|
| `format`, `name`, `game` | `"pokenav-map/1"`, the map's name, the game it is from |
| `source`, `status` | free text: where the cells come from (a decompilation and its commit, an image, console runs) and how far they are trusted (which console checks back them, which checkpoints pass on them) |
| `encounters` | where wild battles start: a list of `grass`, `water`, `cave` (every walkable tile); `[]` for none (towns, buildings, gyms); absent, the cells decide (`grass` if there is tall grass, `water` if there is water; a cave must say so) |
| `legend` | character → `{"blocked": bool, "behavior": name}`; both optional |
| `rows`, `elevation` | the cells, top row first; elevation defaults to 0 |
| `points` | named tiles (`name`, `tile`, `proof`: how a walk proves it is there) |
| `npcs` | `name`, `tile`, `facing`, `sight` (trainers), `wander` (`low`, `high`, `rate`) |
| `signs` | `name`, `tile`, `facing` (the way the player faces to read it) |
| `buildings` | `name`, `kind` (`pokecenter`, `mart`, ...), `door` |
| `warps` | `tile`, `to_map`, `to_warp` (index into that map's warps) |
| `connections` | `direction`, `map`, `offset` (the other map's x or y is this map's minus `offset`) |
| `notes` | `text` and `source`: where each fact came from |
| `image` | `source` (the picture's file or page), `origin` (pixel of tile (0, 0)'s corner), `tile_px` |

Tiles are `[x, y]`. Example: [examples/tiny_town.json](examples/tiny_town.json).

```python
from pokenav.grid.maps import schema
town = schema.load("docs/examples/tiny_town.json")
town.point("DOORSTEP").tile        # Tile(x=1, y=1)
schema.dump("out.json", town, {"#": WALL, ".": OPEN, "D": DOOR})
```

## Text grids (`maps.textgrid`)

The legend is one two-way table between characters and cell kinds
(`textgrid.STANDARD`), used to parse, serialize and show grids:

| Char | Cell | Char | Cell |
|---|---|---|---|
| `#` | wall | `.` | open ground |
| `,` | tall grass | `v ^ < >` | ledge, crossed south / north / west / east |
| `D` | door (walk into) | `W` | warp (step onto) |
| `S` | sign | `~` | water |
| `=` | counter | `i` | ice |
| `R` | rock (Rock Smash opens it) | | |
| `2 8 4 6` | forced move S / N / W / E | `?` | unknown |
| `N` | an NPC on open ground (an object; the cell under it is `.`) | | |

A `Legend` can add characters for NPCs facing a way, or other cell kinds;
each character must stand for one kind and each kind have one character.

The text format is rows of legend characters with `//` comments:
`// Map: name`, named points as `//   NAME x y`, and an optional elevation
layer after `// Elevation:`. `textgrid.parse(text)` reads it into a map file
and `textgrid.serialize(map_file)` writes it back. Convert and show from the
command line (`pokenav.cli.textgrid`):

```sh
PYTHONPATH=python python3 -m pokenav.cli.textgrid show docs/examples/tiny_town.json
PYTHONPATH=python python3 -m pokenav.cli.textgrid convert route.txt route.json
```

## The world (`maps.world`)

A `World` holds map files by name. A `Place` is `(map, tile)`.

- **Connections**: a step off an edge with a connection lands on the other
  map, shifted by the connection's offset (the other map's x, or y for east
  and west, is this map's minus the offset). An edge with no connection is a
  wall. A connection to a map that is not loaded leaves the known world
  (`Edge`).
- **Warps**: entering a warp tile lands on the warp it names (`to_map`,
  `to_warp`). Arriving through a door, the player steps out of it, south.

`movement.world_step` and `world_walk` apply the step rules across maps; a
warp gives `Warped(state, facing)`.

## Objects (`maps.objects`)

Questions about the map file's NPCs, signs and points on a grid:

- `sight_tiles(grid, npc)`: the line a trainer sees, up to `sight` tiles,
  ending at a blocked cell (a ledge too) or another object;
  `watched_tiles(map_file)` lists who sees each tile.
- `reading_tile(sign)`, `can_read(sign, tile, facing)`: signs are read from
  the tile in front of them, facing them.
- `blocking_tiles(map_file, Blocking.NONE | STATIC | ALL)`: the tiles a router
  treats as taken: none, NPCs that stand still, or also every tile of each
  wanderer's patch.
- `walls_around(grid, tile)` and `is_corner`: the directions that hold the
  player on a tile. A corner (walls at right angles) is an anchor: two walks
  end on it from anywhere nearby.

Wanderers are moving walls. Only walls, signs, doors and NPCs that stand
still pin a row or column: a stop next to a wanderer's patch means "somewhere
near it" until a later leg confirms where the player is (`held_at` never
counts an NPC as a wall). A plan treats every tile of the patch as taken
(`Blocking.ALL`), the runtime walker's `avoid` tiles; where a route must cross
a patch, it uses a timed hold and then a wall stop, not a walk until still,
since a wanderer's steps keep the screen moving.

`World.off_map_fraction(place, viewport)` is the black share of the screen
around a place, counting connected maps as shown. A small room never fills
the screen, so screen checks (battle detection, "stopped moving") must not
assume a full-screen map. FRLG's viewport is `pokenav.games.frlg.VIEWPORT`.

## FRLG import (`maps.pret`, `games.frlg`)

pret data is not committed (pokefirered has no license file); the importer
reads a local checkout. `maps.pret.Checkout(root, game)` reads
`layouts.json`, each layout's `map.bin` (metatile, collision, elevation per
tile), the tilesets' `metatile_attributes.bin` (behavior) and each map's
`map.json` (connections, warps, objects, signs). The game-specific numbers
(primary tileset size, behavior table, elevation rules, viewport) are in
`pokenav/games/frlg.py`; the command line is `pokenav.cli.import_frlg`.

```sh
PYTHONPATH=python python3 -m pokenav.cli.import_frlg ~/pokefirered Route1 PalletTown --out /tmp/frlg
# wrote /tmp/frlg/Route1.json (24 x 40)
# wrote /tmp/frlg/PalletTown.json (24 x 20)
PYTHONPATH=python python3 -m pokenav.cli.textgrid show /tmp/frlg/Route1.json
```

Known simplifications: water always blocks; NPCs hidden by a flag are
imported with the flag in their note; signs readable from any side are stored
as read facing north; door mats (arrow warps) fire on the step onto them,
while the game fires them on a press of their direction while standing on
them.

## Sinnoh decomp import (`decomp`, `cli.decomp`)

The DS Sinnoh games' maps are generated from pret/pokediamond or
pret/pokeplatinum, read from a local checkout (or a copy with the same
relative paths; pret data is not committed). `decomp.landdata` decodes a
land data file (a 16-byte header, then 1024 u16 tile attributes for a
32 x 32 cell: bit 0x8000 blocks, the low byte is the behavior) and the map
matrix that places cells in the world (world tile (x, z) is in cell
(z // 32, x // 32)); `decomp.events` reads the objects, warps and sign
events (Platinum's JSON or Diamond's binary records); `decomp.repos` knows
each repository's paths and names Diamond's numbered sprites and maps from
its constants; `decomp.generate` turns a selection of matrix cells into a
map file:

- cells from the attributes: tall grass, water (always a wall to a walker),
  ledges by direction, doors and cave mouths (walked into), warp tiles
  (stood on), ice and forced moves; signposts become `sign` cells and sign
  records, Rock Smash rocks `rock` cells; item balls, Strength boulders and
  Cut trees are standing objects (they block until removed); people are
  NPCs with facing (from `LOOK_*`), sight (trainers) and wander rectangles
  (from the movement ranges); objects a story flag hides go into a note;
- warps, and connections from the matrix cells past each edge, assuming
  each neighbour is generated whole (cell (0, 0) at its top-left);
- `encounters` from the tiles (grass, water, cave floor); `source`, a note
  and `status` naming the repository, commit and files.

Simplifications: one-way blocks are plain ground and two-tile ledges plain
ledges (both listed in a note); heights live in the land data's BDHC blob,
not per tile, so elevation is 0; a tile the loaded cells do not cover is
`unknown`. `--component x,z` keeps only the walkable component holding a
world tile and turns the rest unknown, so a game map with two walkable
regions becomes two map files (one map, one connected component; ledges and
rocks join tiles, water does not). `--keep old.json` carries a hand-edited
file's points, buildings, notes, status and NPC names over.

```sh
PYTHONPATH=python python3 -m pokenav.cli.decomp --repo ~/pokediamond --source pokediamond \
    --name "Route 204 South" --cells 22,5 --events 330 --component 171,705 \
    --keep games/bdsp/maps/route_204_south.json --out games/bdsp/maps/route_204_south.json
# wrote games/bdsp/maps/route_204_south.json (32 x 32), 1 walkable component
```

Cells are matrix (row, col); the events file is a narc number for Diamond
(the zone events column of `arm9/src/map_header.c`) or a stem for Platinum
(`route_204_south` for `res/field/events/events_route_204_south.json`).
Diamond is the source for BDSP, which keeps Diamond/Pearl's layout; the
story maps' land data is byte-identical between Diamond and Platinum apart
from Jubilife's Global Trade Station block.

## BDSP maps (`games/bdsp/`, `games.bdsp`)

The story's first maps are generated from pret/pokediamond and are map files
in `games/bdsp/maps/`: Route 201, Sandgem Town, Route 202, Jubilife City,
Route 203, Route 204 South, the Ravaged Path and Route 204 North. Each
file's `source` names the commit and files, its `status` which console
checks back it, and its notes carry the console-verified anchors and the
known differences between BDSP and the decomp (the Route 201 Potion giver
wanders in BDSP; one-row and one-column questions on Sandgem Town, Route
202, Jubilife and Route 203; a wall column on Route 204 North) as notes,
not patches. Route 204 is two maps because its halves meet only through
the Ravaged Path. The grids traced from Bulbapedia's DP images before
(12 px rows for 16 px columns) are replaced; their console facts were
translated into these frames.

`games.bdsp.story_world()` joins all eight at their edges and through the
cave's doors. Standing NPCs are walls in these worlds: on the console a
standing trainer stops a held walk.

`games/bdsp/wall_hits.json` lists measured walks (start, direction, where
the player stopped, tiles, held or not), where the maps join, which doors
warp where, and `pending` measurements the decomp does not reproduce; the
tests check the maps against every entry but the pending ones. Add a
measurement there when a walk on the console disagrees with the map, then
fix the map file or record the difference in its notes.

## Drawing routes (`maps.render`)

Routes, legs and belief sets are drawn on the map's own picture, lined up
by the map file's `image` entry, or in flat colors for a map without one;
ASCII is for tests and terminals. Images are not committed: download the one
named in the map file's `image.source`. The BDSP maps have no `image`: the
Bulbapedia DP maps have 12 px rows for 16 px columns, so they cannot be
lined up with a tile grid. The command line is `pokenav.cli.render`:

```sh
# text
PYTHONPATH=python python3 -m pokenav.cli.render games/bdsp/maps/route_202.json \
    --path 19,22 30,22 30,19 --region 29,19 30,19
# over the picture (a map file with an image entry)
PYTHONPATH=python python3 -m pokenav.cli.render docs/examples/tiny_town.json \
    --path 0,1 2,1 --image tiny_town.png --out town.png
```

`--path` takes waypoints; each consecutive pair is one straight leg. Legs are
drawn as bars in alternating colors, the start as an outlined square, the
end as a filled one, and each `--region` as tinted tiles. Without `--image`,
`--out` draws the cells in flat colors. `pokenav.png` reads and writes the
PNGs with the standard library only.
