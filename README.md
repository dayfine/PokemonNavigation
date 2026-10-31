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
| `python/pokenav/` | The library, Python 3.8+, standard library only. Navigation on flat 2D tile grids (geometry, maps, movement, routing) is in `pokenav/grid/`; later physics, simulation and traces sit next to it. Core modules know no game; game-specific code is in `pokenav/games/`. |
| `python/tests/` | `unittest` tests, one file per module. |
| `games/<game>/` | Per-game data: maps, named points, measured physics parameters. |
| `measurements/` | Raw console measurements (what was pressed, what happened), so parameters can be refit. |
| `docs/` | The mapping process, the physics to measure, prior art, and the roadmap. |

## Develop

Needs only Python 3.8 or newer. From the repository root:

```sh
python3 -m unittest discover -s python/tests -t python          # all tests
python3 -m unittest discover -s python/tests -t python -p 'test_package.py'  # one file
```

Tests that read a real pokefirered checkout run only when
`POKEFIRERED_DIR` points at one (`POKEFIRERED_DIR=~/pokefirered python3 -m
unittest ...`); pret data is never committed.

GitHub Actions runs the same command on Python 3.8 and 3.12 for every pull
request (`.github/workflows/tests.yml`).

Conventions:

- Every module and class starts with a comment saying what it is for.
- Numbers that mean something get a name and a note on where they come from.
- Keep functions short and flat; split a long or deeply nested one.
- Each command-line tool documents an example input, its output, and the
  command that runs it.

## Status

Building the Python library one small PR at a time. See
[docs/ROADMAP.md](docs/ROADMAP.md).
