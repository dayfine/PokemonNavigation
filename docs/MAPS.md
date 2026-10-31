# Map data

How a map is held in `pokenav.maps`. Code: `python/pokenav/maps/`.

## Cells (`maps.model`)

A map is a grid of cells, row 0 at the top, x east and y south. Each cell has:

| Field | Values | Meaning |
|---|---|---|
| `blocked` | true / false | a plain step onto it is refused |
| `elevation` | 0 to 15 | compared by the movement rules; what each level means is per game |
| `behavior` | `Behavior` | what the tile does besides blocking |

Behaviors: `none`, `ledge_north|east|south|west` (crossed one way, with a
hop), `door` (walk into it to warp), `warp` (step onto it to warp), `water`,
`tall_grass`, `sign`, `counter`, `ice`, `forced_north|east|south|west`, and
`unknown` (not mapped; may be an exit, so neither a wall nor walkable).

A tile off the grid has no cell; the map says which edge it lies past, and the
world (maps joined by connections) decides what is there.

### Screen coverage

A `Viewport` is the window of tiles the game draws around the player. A map
smaller than the viewport (a 6 x 6 house on a 15 x 10 screen) always shows
black around it, which screen checks such as battle detection must allow for:
`MapGrid.off_map_fraction(tile, viewport)` gives the black share of the
screen while standing on `tile`.
