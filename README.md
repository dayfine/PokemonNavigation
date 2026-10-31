# PokemonNavigation

Navigation for bots that play 2D tile-based games through a controller and a
capture card: they press buttons, hold a stick for some milliseconds, and see
only the screen. Starting with Pokémon Brilliant Diamond / Shining Pearl
(Switch) and FireRed / LeafGreen, but nothing here is tied to one game.

It covers four things:

- **Maps**: tile grids built from map images and decompilation data, then
  checked on the console (walls, signs, doors, exits, NPCs, ledges).
- **Physics**: a measured model of how the player moves for each input: how
  far a hold or a tap goes, turning, running and biking, collisions by
  direction, half tiles and diagonals, and how late the "stopped moving"
  check is.
- **Planning**: routes over the grid that stay robust when a move goes a tile
  long, scored by how many unprotected moves they take, how many times they
  must localize, and how many turns.
- **Simulation**: the same route code run against a simulated game many times,
  so a route is scored before it costs a console run.

The bots that use it live elsewhere; the first is
[Arduino-Source](https://github.com/PokemonAutomation/Arduino-Source)'s
AutoStory programs.

## Layout

| Path | What |
|---|---|
| `cpp/` | Core library, C++17, no dependencies: grid, physics model, planner, simulator. Meant to be vendored by bots. |
| `python/` | Tools: map import (images, pret data), measurement analysis, plots, route drawing. |
| `games/<game>/` | Per-game data: grids, measured physics parameters, landmarks. |
| `measurements/` | Raw console measurements (what was pressed, what happened), so parameters can be refit. |
| `docs/` | The mapping process, the physics to measure, the trace format. |
| `scripts/` | Helpers for the lab, e.g. `collect_bdsp_trace.sh` after a console run. |

## Build and test

```sh
cmake -S cpp -B build && cmake --build build -j4 && ./build/pokenav_tests   # -v for plans and statistics
cd python && python3 -m unittest discover tests
```

## Tools

- `python3 -m pokenav.traces extract <SerialPrograms.log> [--since TIME] [--out FILE.jsonl]`:
  movement traces from console runs ([docs/TRACES.md](docs/TRACES.md)).
- `python3 -m pokenav.maps overlay <grid> -o out.svg`: a grid (and a run's
  routes) over its map image; `pokenav/maps/levels.py` reads walkable tiles
  by level from a map image.

## Status

The grid, leg planner, robust planner, physics model and simulator are
ported from Arduino-Source; traces are recorded from every BDSP console run.
See [docs/ROADMAP.md](docs/ROADMAP.md).

Parts are ported from Arduino-Source (MIT); see [NOTICE](NOTICE).
