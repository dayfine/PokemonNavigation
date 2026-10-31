# Physics to measure

Each item is a parameter of the movement model. A value is either measured
(with the measurement in `measurements/`) or a guess, and is marked so. Values
below are what has been seen on the console so far.

Game-specific plans: [BDSP](../games/bdsp/MEASUREMENTS.md).

## Inputs and distance

- **Tap**: a stick hold of N ms from standing still. How many tiles, by N, as a
  distribution. BDSP (measured 2026-10-31): a 160 ms stick hold moves 0.9 to 1.2
  tiles; a 160 ms D-pad tap moves exactly one tile. See
  [games/bdsp/MEASUREMENTS.md](../games/bdsp/MEASUREMENTS.md).
- **Runs of taps**: taps with a gap of G ms between them. BDSP: six 160 ms taps
  400 ms apart moved 6 tiles by hand and 7 on one run; six taps that each
  waited for the screen to settle moved 7.
- **Holds**: a continuous hold of N ms: tiles as a function of N, walking,
  running (B held) and biking; the start-up and stop-down time.
- **Diagonals and analog**: what a diagonal stick does (BDSP has an analog
  stick: does it move diagonally, or pick an axis, and which?), and the dead
  zone.
- **Half tiles**: whether the player can end between tiles (BDSP: a turn and
  nudge east or west seemed to move half a tile near the School door).

## Turning

- A tap toward a different direction turns without a step (BDSP: 100 to 150 ms).
- A tap toward the direction already faced is a step (BDSP: seen as r161c,
  where a turn north right after asking north walked into the plaza).
- How long the turn takes before the next input counts.

## Collisions

- Walls, by direction: one-way edges (ledges), steps, counters you talk over.
- NPCs: they block; how they wander (patch, step rate); whether a wanderer
  makes a walk stop at a random place (BDSP: the green-haired NPC at Jubilife's
  crossing).
- Signs: block, and read only from the tile they face.
- Doors and warps: which tile and facing take you through; where you come out.

## Sensing

- "Stopped moving": how long after the real stop the screen reads still,
  especially near animation (BDSP: Jubilife's TV screen delayed it past 14
  tiles' time).
- Camera: how a tile offset shows on screen (perspective in BDSP: an NPC on
  your row can look a row higher), for locating NPCs and landmarks from a
  screenshot.
- Banners, fades, dialog boxes: how long they take to show.

## Other

- Biking, surfing, ice, spin tiles, tall grass (encounters interrupt a walk).
- Time of day: lighting changes detectors (lamps lit at night).
