"""PokemonNavigation: maps, movement and route planning for 2D tile games.

The package is the reference for how a bot that only presses buttons and
reads the screen can find its way across a tile map. It is plain Python 3.8+
with no dependencies, so bots and tools can import it or port it as they need.

Modules are added one at a time; see docs/ROADMAP.md for the plan. Core
modules know nothing about any one game; game-specific knowledge lives in
`pokenav.games` and in the data under `games/<game>/`.
"""

__version__ = "0.1.0"
