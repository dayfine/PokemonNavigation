# Roadmap

The library is built in Python as a chain of small PRs, each with its own
tests and docs. The full plan, and the review that shaped it, is
[issue #7](https://github.com/dayfine/PokemonNavigation/issues/7).

## A. Foundations

1. Package skeleton and CI.
2. `geometry`: directions, tiles, steps.

## B. Map data

3. `maps.model`: cells (collision, elevation, behavior) and one map.
4. `maps.schema`: the JSON map file, the source of truth for a map.
   `maps.textgrid`: the character legend as a two-way table, to parse, serialize
   and show grids as text.
5. `movement`: what one press does on one map (walls, ledges, elevation).
6. `maps.world`: maps joined by connections and warps.
7. `maps.objects`: NPCs, signs, trainers' sight, named points, the viewport.
8. `maps.pret`: FRLG import from a local pokefirered checkout.
9. BDSP maps: the console-checked grids as map files.
10. `maps.render`: routes and belief sets drawn over the Bulbapedia map image;
    ASCII for tests.

## C. Routing

11. `routing.shortest`: shortest paths with turn and grass costs.
12. `routing.legs`: steps joined into legs; legs that end at a wall preferred.
13. `routing.belief`: the robust planner over sets of possible tiles.
14. `routing.score`: routes ranked by unprotected moves, localizations, turns
    and grass.
15. `routing.localize`: leg sequences that bring a region to one tile.

## D. Physics and simulation

16. `physics`: the movement model as data, and `docs/MEASURING.md`.
17. `sim`: the simulator and Monte Carlo runs.

## E. Traces

18. `traces`: movement traces from console runs.
19. Fitting physics parameters from traces.
