# Roadmap

Done so far (2026-10-30): prior art (1); the port (2) of the grid, map set,
leg planner, robust planner and the simulator with its physics as data (3,
first cut); movement traces from every BDSP console run (6, first cut,
[TRACES.md](TRACES.md)).

1. **Prior art.** What the decompilations, speedrun and TAS communities, and
   other bots already know: map and collision data, frame data, how other bots
   localize and pathfind. Write it up in `docs/PRIOR_ART.md`.
2. **Port what exists.** From the Arduino-Source BDSP AutoStory work (MIT):
   - tile grid and grid parsing (`Pokemon_TileGrid`, `devtools/maps`);
   - the leg planner and the robust planner (belief sets: walls collapse them,
     open legs grow them);
   - the movement simulator and Monte Carlo runner (`bdsp/grid-sim`), made
     game-agnostic: the game plugs in actions, the physics model is data.

   Ported: `cpp/` `Grid`, `TileGrid` (walk to wall, tile planner, robust
   planner with `RobustPlanCosts`, trainer sight), `LegPlanner`, `MapSet`,
   `Simulator` (turns, taps, holds, walks until stopped, wanderers, Monte
   Carlo, playing robust plans) with `PhysicsModel`; `python/pokenav/maps/`
   (grid files, `levels.py`, SVG overlay, route log reader, Bulbapedia
   fetch); Route 202 and the simulator's Poketch Company grid as
   `games/bdsp/maps/*.txt`. Remaining:
   - `Pokemon_LegWalker` (walks a leg, clearing interrupts): needs the bot's
     video inference; port it as an interface once a second bot uses it.
   - `Pokemon_StoryEvents` (checkpoints, events, run state) and the BDSP
     action adapter (`JubilifeActions`): bot code, stays in Arduino-Source;
     the simulator takes trials as functions instead.
   - The other BDSP grids (Route 201, Sandgem Town, Jubilife City, Route
     204, Ravaged Path, Oreburgh Mine) and the story map set's offsets, with
     their console-checked plan tests.
   - The simulator's BDSP specifics left out: signs and NPC talk (OCR
     chances, dialog times), scripted approach legs.
3. **Physics model as data.** A parameter file per game (`games/<game>/physics`)
   with each value marked measured or guessed, and a measurement log format
   so values are refit from `measurements/`.
   First cut: `games/bdsp/physics.txt` (format in `cpp/include/pokenav/Physics.h`),
   with only our own input timings marked measured. Next: fit walking speed,
   walk overhead and tap/hold distances from `measurements/bdsp/` traces
   once records carry true positions.
4. **Route scoring.** Score a route by the chance it succeeds in simulation,
   its time, its unprotected moves (open legs and risky turns, weighted by
   their margin), its localizations, and its turns. Planner proposes, the
   simulator scores.
5. **Mapping process.** The map → route → walk process, how to measure a map
   on the console, and per-game landmarks.
6. **Measurement harness.** Scripted input batches (taps, holds, turns by
   facing, diagonals) and screen analysis that turn console runs into
   measurement records.
   First cut: `python/pokenav/traces` turns the lab log and Command File
   Runner results into records of inputs and walk outcomes
   (`scripts/collect_bdsp_trace.sh` after each run). Next: positions from
   screenshots, a screen reading after timed holds, and scripted batches.
7. **FRLG.** Import maps and collision from the pokefirered decompilation;
   Gen 3 movement frame data.
