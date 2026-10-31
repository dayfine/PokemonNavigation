# BDSP measurement plan

BDSP's movement is analog: the player stands at any position, not on a tile
grid, so a stick hold of a fixed length moves about one tile, not exactly
one. This plan lists what to measure on the console so that routes can say
how far a move goes and how sure it is. The general parameters are in
[`docs/PHYSICS.md`](../../docs/PHYSICS.md). Each result is a record in
`measurements/bdsp/`.

Measurements are made with the lab's Command File Runner (`walk`, `stick`,
`shot`, `shots`, `history`) on the lab console. Each one starts from an
anchor the game fixes: a save at a counter, a wall, or a doorstep.

## Open questions (2026-10-31)

| # | Question | Batch | Why it matters |
|---|---|---|---|
| 1 | How far does one 160 ms hold move, from standing still? | From a wall, 20 holds, each followed by `shot`; read the position against floor tiles. | One-tile steps: the gym door was 19 steps by hand and 18 by the program (r208d). |
| 2 | Do stops snap to the tile grid? | Holds of 100, 120, 140, 160, 180 and 200 ms from a wall, each followed by `shot`. | Whether error adds up over N steps or resets each step. |
| 3 | Drift over N steps | N = 5, 10 and 19 one-tile steps from a wall, 3 times each, ending against a landmark. | How far a counted leg can go before it needs an anchor. |
| 4 | Where does leaving a Pokemon Center put you? | From the counter, exit 3 times each with: one walk until still; one-tile steps until outside; a single long hold. `shot` on the doorstep each time. | The exit was blamed for a tile's error, but that was not measured. |
| 5 | How far does a turn or a nudge move you? | Facing another way: a 100 ms tap, a 50 ms tap and an 80 ms tap, 5 times each, `shot` before and after. | A turn is a tap and moves the player (s03e2 drifted a third of a tile per try). |
| 6 | Door fade timing | Step into a door with `shots 12 250`; find when the screen goes black and for how long. | The gym door's black came about 2 s after the step, after the step's own watcher had stopped. |
| 7 | One tile's scroll against a new scene | `shot` before and after a one-tile step in the open, against a wall, and through a door. | The view change for a scroll (106 to 119) and for a door (121) were too close to tell apart. |
| 8 | Screen thresholds | Mean brightness and Center floor share at Center inside, outside, mine, gym and routes, by day and night. | The brightness and floor-share thresholds used so far came from about 10 frames. |
| 9 | Pushing against a facade | Push north at the gym's and the Center's fronts, with 50 ms and 160 ms side taps. | Nudges barely moved against a facade; pushes slid back. |

## Recording

For each batch, keep the `.out` and the shots and write one record per
measurement: what was pressed, from which anchor, what was seen (a tile
offset read from the shot, or a timing), and the build. Write the answer
back into this table and into `docs/PHYSICS.md` as measured, with the record
it came from.
