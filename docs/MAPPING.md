# Mapping process

Moved from Arduino-Source devtools/maps (fork PR #83).

## Map, route, walk: getting a route to work on the console

A route that fails on the console has failed in one of three layers. Find
which one before changing anything, and fix that layer:

| Layer | What it is | How it is checked |
| --- | --- | --- |
| Map | the tile grid: walls, signs, doors, exits, NPCs | only by measuring on the console |
| Route | the legs a checkpoint walks | offline, by the plan tests, before any console run |
| Walk | holding the stick until something stops us | console runs; the route absorbs its error |

- **Map**: a leg planned "to wall" ran out of time, or went through a
  transition, or stopped where the grid has no wall. Measure that place
  again; don't tune the walker.
- **Route**: the plan used something it must not, such as an exit as a wall or
  a long open leg. Add the plan test that would have caught it.
- **Walk**: map and plan are right, but a hold moved a different number of
  tiles, or someone stood in the way. End more legs on walls, or add a
  re-anchor.

### Measuring a map

The images above give a first grid. Before a route depends on it, measure it
with the Command File Runner's `walk x y`, which holds the stick until the
screen stops changing and prints how long it moved. Don't use timed `stick`
holds for this: on BDSP the same 300 ms hold moved one row on one try and two
on the next. Write down:

- borders and exits: where each edge stops you or takes you elsewhere;
- anchors: tiles a walk can prove it stands on (two walls, a door, the tile
  beside a sign), and how each is proven;
- distances between anchors, as `walk` measures them;
- objects: the row and column of each sign, NPC and door relative to the walls
  around it, which sides it can be read or talked from, and whether the tiles
  next to it are open.

Decide rows by stops and sign reads, never by eye: at the overworld camera's
angle an NPC on your row looks a row higher, and a sign a row below the trees
can look right under them. Mark exits (steps, walkable edges) `D`, never `#`;
a `#` there is a wall the planner will walk "to", and off the map. Put what
was measured in the data file's header ("Checked on the console: ...").

### Planning the route

- Start and end each checkpoint on an anchor, and save there, so a reload
  starts exactly there; its first event checks the anchor and re-anchors if
  the check fails.
- End every leg against something: a wall, a sign, an NPC who answers. Keep
  open legs to a tile or two, and follow each with a leg that shows whether it
  took.
- Out and back can take different rows; pick each direction's legs for the
  walls they end on.
- A sign is a gate: walk until it stops you and press A. If it doesn't open,
  you are not on its row.
- Check every planned walk offline, and draw it with `overlay` before the
  first console run.

## Tools

Ported from Arduino-Source devtools/maps (`python/pokenav/maps/`).

### `levels.py`: walkable tiles, by level

Towns and caves have levels: terraces and ledges bordered by rock rims, joined
only by stairs. Judging each 16 px tile by its colours alone walks a route off
one level onto another wherever a rim stripe is thin, so `levels.py` works at
pixel resolution first:

1. Each pixel is walkable (paving, road, grass, curb), stairs, or blocked
   (rims, roofs, trees, water).
2. Walkable pixels are flood-filled into regions; a rim of any width keeps
   two levels apart.
3. Each blob of stair pixels joins the regions it touches.
4. Each tile takes the region holding at least half its pixels. A step is
   allowed between tiles of the same region, or onto and off a stair tile
   that touches both.
5. A breadth-first search gives the route; the output lists its corners.

```sh
swiftc -O python/pokenav/maps/swift/png2bmp.swift -o png2bmp     # sips mangles palette PNGs
./png2bmp Veilstone_City_DP.png veil.bmp
python3 python/pokenav/maps/levels.py veil.bmp out/veil --offset 8,9 \
    --stairs 704,290 --stairs 512,527 --stairs 80,665 ...   # one pixel per staircase
    --from 605,474 --to 82,470                              # pixel points
# writes out/veil_regions.bmp, out/veil_grid.txt, out/veil_route.txt
swiftc -O python/pokenav/maps/swift/draw_route.swift -o draw_route
./draw_route Veilstone_City_DP.png route.png "$(head -1 out/veil_route.txt)"
```

Options for harder maps:

- `--profile town|sandtown|oreburgh|cave`: colour rules. `oreburgh` counts the
  conveyor belts as ground (we walk under them; the pillars block).
  `sandtown` adds dirt roads and sand (Sandgem) to `town`.
- `--height H`: stretch a squashed image back to H pixels tall. Oreburgh
  Mine B2F is 512x395 for a 512x512 map: its rocks are 16 px apart across
  and 12.5 px down.
- `--objects on`: rocks, boulders, crates and people standing on the floor
  block the tile under their feet, even when drawn smaller than a tile or
  off the grid.
- `--edits FILE`: tiles opened or blocked from what the console showed,
  `open ROW COL0 COL1` / `block ROW COL0 COL1`; edits apply before objects.
  E.g. rows the coal block's edge is drawn over are walkable, and people
  touching the coal block are not found as objects.

`games/bdsp/maps/examples/` (the grids; the route images stay in Arduino-Source) has Veilstone City's levels and two routes to the Gym (from the
Pokémon Center and from Route 215). Both reach the Gym's terrace only by its
south-west stairs. Oreburgh: the Pokémon Center to the mine is one column
straight south (checked on the console), and Mine B2F's route to Roark
with its edits file.

Check per map:

- **Tile alignment** (`--offset`): not always (0, 0). For Veilstone it is
  (8, 9), read from the edges of the three-tile stairs at the bottom.
- **Colours**: the rules are for Sinnoh towns. Caves need their own.
- **Stairs** are given by hand, one pixel inside each.
- **Not modelled:** one-way ledges and people. Static NPCs are added from
  what the console shows.

### Overlay: a data file's grid, and a run's routes, over the map

`python3 -m pokenav.maps` (from `python/`) (standard library only) draws a navigation data
file's grid over the map image it was read from, as SVG, and optionally the
walks a console run planned and walked:

```sh
python3 -m pokenav.maps fetch Sandgem_Town_DP.png          # into ~/.cache/maps
python3 -m pokenav.maps overlay path/to/Data/..._SandgemTown.cpp -o sandgem.svg
python3 -m pokenav.maps overlay path/to/Data/..._SandgemTown.cpp \
    --log "$HOME/Library/Application Support/SerialPrograms/Profiles/<profile>/SerialPrograms.log" \
    --last 3 -o sandgem-run.svg
python3 -m unittest discover tests
```

It reads a grid text file (`games/<game>/maps/*.txt`), or a C++ data file's `R"(...)"` rows and `const TilePos NAME{x, y};` tiles, and
its header comment for the image (`(Name.png, W x H px)`) and where tile (0, 0)
starts (`starts 8 px in from the left edge`). Walls are red, tall grass green,
ledges purple, signs orange, doors blue, every fifth row and column numbered.
With `--log`, a leg planned "to wall" that stopped on anything but `blocked`
is marked yellow: the grid has a wall where the game doesn't.

Sandgem Town, levels.py against the console-checked grid: with `sandtown`
and `--objects on`, rows 0..7 agree but for two lit door fronts read as
objects (we stood on (17, 7)) and the Lab's front, (6..9, 7), read as blocked
(walked on the console). Lawns, roads and the beach come out as separate
regions with no ledge between them, and the image squeezes rows 7..18 into
7..15, so the south half is taken from the game's collision instead.
