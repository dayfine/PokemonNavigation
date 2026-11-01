"""Pokemon Brilliant Diamond / Shining Pearl: the story maps and how they
join.

BDSP's movement is analog, but the story maps are walked as a tile grid.
The grids are generated from pret/pokediamond (`pokenav.cli.decomp`), whose
land data BDSP keeps, and checked on the console; the map files are in
games/bdsp/maps/, and each one's `status` and notes say what was checked.
A standing NPC stops a held walk like a wall on the console (Route 202's
trainer_a), so the worlds here turn standing NPCs into walls.

    world = story_world()        # Route 201 to the Ravaged Path, joined
    world.across_edge(Place("Route 202", Tile(29, 32)))
    # Place(map='Sandgem Town', tile=Tile(x=29, y=0))

Measured walks to check the maps against are in games/bdsp/wall_hits.json.
"""

import os
from typing import List

from pokenav.grid.maps import schema
from pokenav.grid.maps.objects import with_static_npcs_as_walls
from pokenav.grid.maps.schema import MapFile
from pokenav.grid.maps.world import World

#   games/bdsp, from python/pokenav/games.
GAME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "games", "bdsp")
MAPS_DIR = os.path.join(GAME_DIR, "maps")
WALL_HITS = os.path.join(GAME_DIR, "wall_hits.json")

#   Map file names by map name.
MAP_FILES = {
    "Route 201": "route_201.json",
    "Sandgem Town": "sandgem_town.json",
    "Route 202": "route_202.json",
    "Jubilife City": "jubilife_city.json",
    "Route 203": "route_203.json",
    "Route 204 South": "route_204_south.json",
    "Ravaged Path": "ravaged_path.json",
    "Route 204 North": "route_204_north.json",
}

#   The maps of the story's first stretch, joined at their edges and through
#   the Ravaged Path's doors. Route 204 is two maps: its halves meet only
#   through the cave (one map, one connected component).
STORY_MAPS = list(MAP_FILES)


def load_map(name: str) -> MapFile:
    """The map file for map `name`, as stored (NPCs are objects)."""
    return schema.load(os.path.join(MAPS_DIR, MAP_FILES[name]))


def world_of(names: List[str]) -> World:
    """The named maps in one world, with standing NPCs as walls."""
    return World(with_static_npcs_as_walls(load_map(name)) for name in names)


def story_world() -> World:
    return world_of(STORY_MAPS)
