# Roadmap

1. **Prior art.** What the decompilations, speedrun and TAS communities, and
   other bots already know: map and collision data, frame data, how other bots
   localize and pathfind. Write it up in `docs/PRIOR_ART.md`.
2. **Port what exists.** From the Arduino-Source BDSP AutoStory work (MIT):
   - tile grid and grid parsing (`Pokemon_TileGrid`, `devtools/maps`);
   - the leg planner and the robust planner (belief sets: walls collapse them,
     open legs grow them);
   - the movement simulator and Monte Carlo runner (`bdsp/grid-sim`), made
     game-agnostic: the game plugs in actions, the physics model is data.
3. **Physics model as data.** A parameter file per game (`games/<game>/physics`)
   with each value marked measured or guessed, and a measurement log format
   so values are refit from `measurements/`.
4. **Route scoring.** Score a route by the chance it succeeds in simulation,
   its time, its unprotected moves (open legs and risky turns, weighted by
   their margin), its localizations, and its turns. Planner proposes, the
   simulator scores.
5. **Mapping process.** The map → route → walk process, how to measure a map
   on the console, and per-game landmarks.
6. **Measurement harness.** Scripted input batches (taps, holds, turns by
   facing, diagonals) and screen analysis that turn console runs into
   measurement records.
7. **FRLG.** Import maps and collision from the pokefirered decompilation;
   Gen 3 movement frame data.
