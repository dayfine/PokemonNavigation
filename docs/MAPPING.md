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
