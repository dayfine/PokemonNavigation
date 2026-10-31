# Prior art

Collected 2026-10-30. Links are the sources; licenses noted for code.

## Map and collision data

- **pret decompilations** ([pokefirered](https://github.com/pret/pokefirered),
  [pokeemerald](https://github.com/pret/pokeemerald)). `data/layouts/layouts.json`
  lists each layout's size, tilesets and `map.bin`. A `map.bin` entry is a u16:
  bits 0-9 metatile, 10-11 collision, 12-15 elevation
  ([global.fieldmap.h](https://github.com/pret/pokeemerald/blob/master/include/global.fieldmap.h)).
  Per-metatile behaviors (ledges, ice, spin tiles, forced movement, warps,
  water, counters) are in `include/constants/metatile_behaviors.h`. This is the
  ground truth for FRLG grids. No LICENSE file in pokefirered.
- **Elevation** ([Porymap manual](https://huderlem.github.io/porymap/manual/editing-map-collisions.html)):
  no stepping between elevations except on transition tiles; "multi-level"
  keeps the previous elevation (bridges). Elevation belongs in the planner state.
- **Porymap** ([repo](https://github.com/huderlem/porymap), LGPL-3.0): map
  editor with a scripting API (`getCollision`, `getElevation`,
  `getMetatileBehavior`) and overlays; useful to show routes on real maps.
- **Gen 4 DS** ([mapping guide](https://ds-pokemon-hacking.github.io/docs/generation-iv/guides/mapping)):
  32x32 grids with a per-square permission file; a likely prior for BDSP.
- **BDSP**: no public collision or navmesh dump found. Leads: the
  [Luminescent Platinum](https://luminescent.team/docs) modding scene and
  BDSP-Repacker/UABEA asset extraction. Otherwise measure on the console.

## Movement physics

- **Gen 3**, from pokeemerald `event_object_movement.c` and
  `field_player_avatar.c`: frames per tile 16 walking, 8 running or surfing,
  6 Acro Bike, 4 and 2 Mach Bike (which ramps up a step at a time and slows
  when blocked, `bike.c`).
- **Turn or step** (pokefirered `field_player_avatar.c`): a direction other
  than the *last movement* direction, while not moving, plays an 8-frame turn
  in place; otherwise a step. Input is read only at tile centres or when
  stopped, so a hold always finishes the tile it started.
- **Wall bump**: a 32-frame walk in place with the `SE_WALL_HIT` sound, which
  could be detected by audio.
- **BDSP**: the maps are grid-based but the player moves freely in any
  direction (analog); NPCs and cutscenes stay on the grid
  ([Game8](https://game8.co/reviews/pokemon-brilliant-diamond-shining-pearl/pokemon-brilliant-diamond-and-shining-pearl-review),
  [GameSpot](https://www.gamespot.com/reviews/pokemon-brilliant-diamond-shining-pearl-review/1900-6417790/)).
  No published speeds. So FRLG can use an exact tile automaton with timing
  noise; BDSP needs a continuous-position model fitted to measurements.

## Bots and agents

- [PokemonRedExperiments](https://github.com/PWhiddy/PokemonRedExperiments)
  (MIT) and [pokegym](https://github.com/PufferAI/pokegym) (MIT): RL with
  PyBoy, reading memory; no pathfinder.
- Claude Plays Pokémon ([writeup](https://latent.space/reading/claude-plays-pokemon/))
  and Gemini Plays Pokémon ([about](https://rentry.org/gpp-about-20250612)):
  location from RAM; navigation on the visible screen; localization from
  pixels was the weak part.
- [pokebot-gen3](https://github.com/40Cakes/pokebot-gen3) (GPL-3.0): memory
  based on libmgba with pret symbols.
- [pokered-scripts](https://github.com/barneyboo/pokered-scripts): mGBA Lua
  A*, adding trainers and signs to the collision grid.

## Planning under uncertainty

1. Lozano-Pérez, Mason, Taylor 1984, preimage backchaining for compliant
   motion: "walk until a wall stops you" is a preimage; plan backward from the
   goal with legs whose stop guarantees the result.
2. Erdmann and Mason 1988, sensorless manipulation: walls collapse the set of
   possible positions as tilting a tray collapses part poses.
3. Synchronizing words (Eppstein 1990): an input sequence that sends every
   start tile to one tile is a formal "one localization" leg.
4. Roy and Thrun 1999, coastal navigation: plan over position and
   uncertainty, preferring routes along landmarks; a principled robustness
   score.
5. Burridge, Rizzi, Koditschek 1999, sequential composition of funnels: each
   leg's end region must fit inside the next leg's safe start region.
6. Dellaert, Fox, Burgard, Thrun 1999, Monte Carlo localization: belief as
   samples, the natural model for BDSP's continuous movement.

## Simulators

- [PyBoy](https://github.com/Baekalfen/PyBoy): fast Game Boy emulator (Red
  and Blue only).
- mGBA (libmgba): run planned inputs against the real FRLG ROM and read the
  true position from memory, to validate the simulator.
- No BDSP simulator found.

## To adopt first

1. Parse pret `map.bin` and metatile behaviors for FRLG grids.
2. Port the Gen 3 timings exactly; simulate only our input timing noise.
3. Validate the simulator against FRLG in mGBA, reading position from memory.
4. Score routes with funnels and preimages plus a coastal-navigation cost;
   compute localizing legs as synchronizing words; particles for BDSP.
5. Show routes and belief sets on real maps (Porymap overlays or our own
   renderer).
