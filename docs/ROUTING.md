# Routing

How routes are planned over a world (`pokenav.grid.routing`).

## Shortest paths (`routing.shortest`)

`shortest_path(world, start, goal, costs, rules, objects)` is Dijkstra over
(where the player is, which way they last moved). Each press costs:

| Weight | Default | For |
|---|---|---|
| `tile` | 1 | each tile walked; a ledge hop walks 2 |
| `turn` | 2 | a press in another direction than the last |
| `grass` | 5 | each tall-grass tile entered (wild battles interrupt a walk) |
| `warp` | 1 | each door or warp taken |

It crosses map edges and warps, follows the elevation rules, and treats
`objects` (places) as taken. `follow(world, start, legs)` walks a route drawn
by hand (a direction and end place per leg) and gives its cost, so drawn and
planned routes can be compared.

### Route 1: the grass weight

`games/frlg/routes/viridian_to_pallet.json` is the hand-drawn line from
Viridian City to Pallet Town (8 legs, 6 ledge drops, 5 grass tiles). With
`turn` 2, a `grass` weight of 5 or more gives the same shape: the same leg
directions, ledges and grass, on the same rows. A weight of 3 or less cuts
through 10 grass tiles to save two turns. Two vertical legs (down the west
side, and down past the row-26 ledge) may run in another column than the
drawn one: for the shortest path every column there costs the same, and the
choice is left to the robust planner and scoring. The test needs a
pokefirered checkout (`POKEFIRERED_DIR`).

## Legs (`routing.legs`)

A bot walks in legs: hold one direction until it has gone far enough or
something stops it. A `Leg` has a direction, the tiles it walks (a hop counts
2), whether it ends `to_wall` (holding on keeps the player there) and
whether it ends in a warp. A `FACE` leg turns without moving.

- `join_legs(world, start, moves)` groups a path's moves into legs; a warp
  ends its leg.
- `plan_legs(world, start, goal, start_facing, goal_facing, costs)` searches
  like `shortest_path` over (place, facing, mid-leg) and adds
  `LegCosts.open_stop` (default 8) for each leg that ends where the player
  could keep going. So of two equal paths it takes the one whose legs end at
  walls, and it adds a face leg when the goal needs a facing.

A person is not a wall (they may walk off), a door or a map edge to an
unloaded map is not either; see `docs/MOVEMENT.md`.

The leg planner alone does not reproduce Route 1's drawn line: with
`open_stop` 8 it ends a leg on the wall at (7, 24) and cuts through 5 more
grass tiles, because the drawn line's legs mostly end in the open. What
makes those legs safe is that each ledge drop pins the row, which the
belief-set planner models.

## Robust plans (`routing.belief`)

The planner tracks a belief: the set of states the player may be in. Each
leg is held one way and ends in one of three ways, which is also what proves
it ended there:

| Leg end | Held until | Belief after |
|---|---|---|
| `WALL` | the player is stopped | each state's stop: a wall collapses a row or column |
| `LEDGE` | the first ledge hop lands | each state's landing: a drop pins the row |
| `OPEN` | about n tiles | each state n - k to n + k tiles on, k from `OpenLegError` |

`OpenLegError(base=1, per=5)` allows `1 + n // 5` tiles of error (a
parameter until the physics model measures it). A leg that may run into a
door, off the loaded maps, onto unknown ground or into a person is refused,
and so is an open leg over a ledge (the hop's time is fixed, so the hold
would not match the tiles). `plan_belief(world, starts, goal, costs)` is A*
over beliefs: each leg costs `per_leg` plus the path weights of its longest
walk and most grass, plus `open_stop` if it ends in the open; beliefs larger
than `max_spread` (5) are refused; the estimate is the longest single-state
walk left to the goal. Each `PlannedLeg` carries its end kind and the belief
after it, for the walker to check on arrival.

Search time grows with the maps: Route 202 plans in well under a second,
the story maps' 3 x 3 start to Sandgem's Pokemon Center in about a second,
but Viridian City, Route 1 and Pallet Town together take minutes, so
`routing.score` proposes and ranks routes there rather than searching.

## Scoring and ranking (`routing.score`)

A route is judged by risk, not length. `score(planner, starts, legs, goal)`
replays the legs and gives a `RouteScore`:

| Field | Meaning |
|---|---|
| `risk` | each open leg ("unprotected move") counts 1 / (1 + margin); the margin is how many tiles of extra error the leg takes before the route fails (up to `max_margin`, 3) |
| `localizations` | legs that shrink the belief (a wall or a ledge landing), past the first |
| `turns`, `turnarounds` | direction changes, and those back the way the route came |
| `grass` | tall-grass tiles crossed, on their own |
| `tiles` | length |

`rank` sorts routes lexicographically (risk, localizations, turnarounds,
turns, grass, tiles) by default, or by a weighted sum with
`ScoreOptions(weights=...)`; `score.WEIGHTS` is a starting set.
`ScoreOptions(ledges_localize=False)` counts ledge legs as unprotected, as
the old planners did. `propose` turns shortest paths under several turn and
grass weights into planned legs (split at each ledge landing), and
`plan_ranked` proposes and ranks. `checks(starts, legs)` lists for each leg
the states the player should be in and what proves it: "wall bump", "ledge
landing", "map banner" (a new map), or "none".

### Route 1 again

With `WEIGHTS` and a grass weight of 2 or more, the top-ranked proposal for
Viridian City to Pallet Town has the drawn line's shape: its 8 leg
directions, 6 ledge drops, 5 grass tiles and rows. As with the shortest path,
its west-side and row-26 columns (7 and 18) differ from the drawn 5 and 20:
nothing in the score tells those columns apart. With grass at 0.5, or
lexicographic ranking (risk first), the top route cuts through 10 to 15 grass
tiles for fewer open legs. The old planner's view, grass at 20 a tile and no
ledges, gives a zigzag with more turns and grass, which ranks below the
drawn line; counting ledges as unprotected adds 6 to the drawn line's risk.
Open legs on FRLG are taken as exact (`games.frlg.OPEN_LEG_ERROR`), a guess
until measured.
