# Map data

How a map is held in `pokenav.maps`. Code: `python/pokenav/maps/`.

## Cells (`maps.model`)

A map is a grid of cells, row 0 at the top, x east and y south. Each cell has:

| Field | Values | Meaning |
|---|---|---|
| `blocked` | true / false | a plain step onto it is refused |
| `elevation` | 0 to 15 | compared by the movement rules; what each level means is per game |
| `behavior` | `Behavior` | what the tile does besides blocking |

Behaviors: `none`, `ledge_north|east|south|west` (crossed one way, with a
hop), `door` (walk into it to warp), `warp` (step onto it to warp), `water`,
`tall_grass`, `sign`, `counter`, `ice`, `forced_north|east|south|west`, and
`unknown` (not mapped; may be an exit, so neither a wall nor walkable).

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
from pokenav.maps import schema
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

## BDSP maps (`games/bdsp/`, `games.bdsp`)

The story's first maps, read from Bulbapedia's DP maps and checked on the
console, are map files in `games/bdsp/maps/`: Route 201, Sandgem Town,
Route 202 and Jubilife City. Each file's notes say how its grid was read and
what was measured. `games.bdsp.story_world()` joins Route 201, Sandgem Town
and Route 202; Jubilife City stays on its own until its stairs are mapped.
Standing NPCs are walls in these worlds: on the console a standing trainer
stops a held walk.

`games/bdsp/wall_hits.json` lists measured walks (start, direction, where the
player stopped, tiles, held or not) and where the maps join; the tests check
the maps against every entry. Add a measurement there when a walk on the
console disagrees with the map, then fix the map file.

## Drawing routes (`maps.render`)

Routes, legs and belief sets are drawn on the map's own picture (the
Bulbapedia map), lined up by the map file's `image` entry; ASCII is for
tests and terminals. Images are not committed: download the one named in the
map file's `image.source`.

```sh
# text
PYTHONPATH=python python3 -m pokenav.maps.render games/bdsp/maps/route_202.json \
    --path 19,22 30,22 30,19 --region 29,19 30,19
# over the picture
PYTHONPATH=python python3 -m pokenav.maps.render games/bdsp/maps/route_202.json \
    --path 19,22 30,22 30,19 --image Sinnoh_Route_202_DP.png --out route.png
```

`--path` takes waypoints; each consecutive pair is one straight leg. Legs are
drawn as bars in alternating colors, the start as an outlined square, the
end as a filled one, and each `--region` as tinted tiles. Without `--image`,
`--out` draws the cells in flat colors. `pokenav.png` reads and writes the
PNGs with the standard library only.
