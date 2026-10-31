# Routing

How routes are planned over a world (`pokenav.routing`).

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
