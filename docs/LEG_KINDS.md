# Leg kinds

How a bot walks each leg of a robust plan (`pokenav.grid.routing.execution`),
and when the planner (`routing.belief`) picks each. The numbers come from each
game's `games/<game>/physics.txt` (`pokenav.physics`).

## Kinds

| Kind | The bot presses | Lands | Belief after |
|---|---|---|---|
| `clip` | the stick, until the player stops against a wall | exactly at the wall | collapses on that axis, from any start along it |
| `ledge` | the stick, until the first ledge hop lands | on the landing row | collapses on that axis |
| `dpad` | N D-pad taps, checking that each moved a tile | N tiles on, within the error model | BDSP and FRLG on foot: exact, so it does not spread |
| `stick` | the stick for the time of N tiles | N tiles on, ± the error model | spreads by the error model |
| `door` | a turn tap if needed, then a hold into the door ahead | through the door; the fade proves it | the warp's arrival |

A first tap toward a new direction only turns the player, so a `dpad` or
`door` leg that starts facing another way costs `turn_tap` more. A plan is a
plain list:

```python
from pokenav.games import bdsp
from pokenav.grid.routing.belief import BeliefPlanner
from pokenav.grid.routing.execution import bot_legs

planner = BeliefPlanner(world, bdsp.belief_costs())
legs = planner.plan(start, goal, facing=Direction.NORTH, bike=False)
bot_legs(legs)    # [("door", "S"), ("dpad", "W", 20), ("door", "N")]
```

With the bike, `("mount",)` and `("dismount",)` come before the first leg
ridden or walked.

## Error model

A counted leg of n tiles may end up to `per_tile * sqrt(n) + overshoot` tiles
from n, rounded to whole tiles (the player starts on a tile's centre, so an
error under half a tile still lands on the planned tile). The square root is
because per-step errors add up like a random walk: on BDSP a stick hold is off
by about ±0.15 tile per tile, and 18 holds came to about half a tile.

| Game, mode | `dpad` | `stick` | Tile cost | Source |
|---|---|---|---|---|
| BDSP, foot | exact | 0.15 per tile: exact to 11 tiles, ±1 from 12 | 1 | measured, games/bdsp/MEASUREMENTS.md results 2026-10-31 |
| BDSP, bike | 0.3 per tile + 0.5 | 0.3 per tile + 1 overshoot | 0.5 | guessed, to measure (below) |
| FRLG, foot and bike | exact | exact | 1; bike 0.375 (6 frames a tile, not 16) | pret |

## When the planner picks each

The planner searches over (belief, facing, mode) and charges each leg its
tiles (times the mode's tile cost), `per_leg`, `open_stop` for a timed stick
hold or a leg that may end off its tile, `turn_tap` and `mount` as above, and
`door` for a door's fade. Legs that would spread the belief past `max_spread`,
or run into a door, edge or person on the way, are refused. So:

- **Known start, exact taps**: `dpad`. 20 taps along Oreburgh's street cost a
  turn tap and 20 tiles; a clip to the street's end and taps back cost more.
- **Uncertain start**: the planner starts from one known tile. A bot that is
  not sure of its tile clips to a wall first (`routing.localize.synchronize`
  finds the legs: a clip brings a belief three tiles wide to one tile), then
  plans. Taps counted from a belief three tiles wide would end three tiles
  wide and miss a one-tile door.
- **`stick`**: only where its error is harmless (short legs, or a clip or
  ledge after it that collapses the spread), and on FRLG where it is exact. A
  20-tile stick hold on BDSP may end a tile off and is refused before a door.
- **`door`**: to end at a door, or to pass into another loaded map.
- **Bike** (only with `bike=True` and a game model that has one): for long
  clips, where the bike's speed pays for getting on. Exact offsets stay on
  foot with `dpad`, since BDSP bike taps are not assumed to be whole tiles.

## Bike measurements (BDSP, planned)

The BDSP bike is obtained in Eterna City; none of its values are measured.
These are the planned measurements; they belong in
games/bdsp/MEASUREMENTS.md's open questions, which are on another branch, so
they are kept here until that lands.

| Parameter | Batch |
|---|---|
| `bike.tile_cost` | Hold from wall to wall on a long straight, on foot and on the bike, 3 times each; the time ratio. |
| `bike.dpad.*` | 10 taps from a wall, 3 times, a shot after each tap: whether a tap moves a whole tile. |
| `bike.stick.per_tile` | Holds of 0.5, 1 and 2 s from a wall, 5 times each, a shot once still. |
| `bike.stick.overshoot` | Let go mid-run, shots every 100 ms until still: the slide after release. |
| `mount` | Time from the bike button to riding, and back. |

## Physics file format

One parameter per line: name, value, status (`measured`, `pret`, `guessed`
or `defined`) and source. Lines starting with `#` are comments.

```
foot.stick.per_tile   0.15   measured  games/bdsp/MEASUREMENTS.md results 2026-10-31 (#1)
bike.tile_cost        0.5    guessed   to measure: hold time from wall to wall, on foot and on the bike
```

Names: `<mode>.tile_cost`, `<mode>.dpad.per_tile`, `<mode>.dpad.overshoot`,
`<mode>.stick.per_tile` and `<mode>.stick.overshoot` for `foot` and
(optionally) `bike`; `turn_tap`, `mount` and `door`.
