"""Tests for the BDSP map files and pokenav.games.bdsp: every map loads, is
one connected component and says where it comes from; named places have the
cells their notes say; the maps join where their exits and doors meet; and
every measured walk in games/bdsp/wall_hits.json ends where it was measured
to."""

import json
import unittest

from pokenav.decomp.generate import walkable_components
from pokenav.games import bdsp
from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.model import Behavior
from pokenav.grid.maps.world import Place
from pokenav.grid.movement import Moved, Warped, WorldState, world_step, world_walk


def place(value) -> Place:
    name, x, y = value
    return Place(name, Tile(x, y))


def load_wall_hits():
    with open(bdsp.WALL_HITS) as f:
        return json.load(f)


class MapFilesTest(unittest.TestCase):
    def test_sizes(self):
        sizes = {
            "Route 201": (64, 32),
            "Sandgem Town": (32, 32),
            "Route 202": (32, 32),
            "Jubilife City": (64, 64),
            "Route 203": (64, 32),
            "Route 204 South": (32, 32),
            "Route 204 North": (32, 32),
            "Ravaged Path": (32, 64),
        }
        self.assertEqual(sorted(sizes), sorted(bdsp.MAP_FILES))
        for name, size in sizes.items():
            grid = bdsp.load_map(name).grid
            self.assertEqual((grid.width, grid.height), size, name)

    def test_every_map_is_one_component_from_pokediamond(self):
        for name in bdsp.MAP_FILES:
            map_file = bdsp.load_map(name)
            with self.subTest(name):
                self.assertEqual(len(walkable_components(map_file.grid)), 1)
                self.assertTrue(map_file.source.startswith("pret/pokediamond@"))
                self.assertIn("generated from the decomp", map_file.status)
                self.assertTrue(any(n.source.startswith("pret/pokediamond@") for n in map_file.notes))

    def test_named_places(self):
        route202 = bdsp.load_map("Route 202")
        self.assertIs(route202.grid.at(route202.point("CATCH_SPOT").tile).behavior, Behavior.TALL_GRASS)
        self.assertEqual(sorted(n.name for n in route202.npcs if n.sight), ["trainer_a", "trainer_c", "trainer_d"])
        self.assertEqual(route202.encounters, {bdsp.schema.Encounter.GRASS})
        sandgem = bdsp.load_map("Sandgem Town")
        for building in sandgem.buildings:
            self.assertIs(sandgem.grid.at(building.door).behavior, Behavior.DOOR, building.name)
        self.assertIs(sandgem.grid.at(sandgem.point("POKEMON_CENTER_SIGN").tile).behavior, Behavior.SIGN)
        self.assertEqual(sandgem.encounters, frozenset())
        jubilife = bdsp.load_map("Jubilife City")
        doors = {b.kind: jubilife.grid.at(b.door).behavior for b in jubilife.buildings}
        self.assertEqual(doors, {"school": Behavior.WARP, "pokecenter": Behavior.DOOR, "tv_station": Behavior.DOOR})
        names = {n.name for n in jubilife.npcs}
        self.assertTrue({"clown_tv_station", "clown_poketch_company", "clown_mart", "poketch_president",
                         "green_haired_man"} <= names)
        self.assertEqual(sorted(n.name for n in jubilife.npcs if n.wander and n.name.startswith(("clown", "green"))),
                         ["clown_mart", "clown_poketch_company", "green_haired_man"])

    def test_ravaged_path_rocks_and_doors(self):
        cave = bdsp.load_map("Ravaged Path")
        self.assertEqual(cave.encounters, {bdsp.schema.Encounter.CAVE, bdsp.schema.Encounter.WATER})
        for tile in [Tile(22, 42), Tile(22, 43), Tile(23, 44), Tile(17, 40), Tile(12, 41), Tile(13, 39)]:
            self.assertIs(cave.grid.at(tile).behavior, Behavior.ROCK, tile)
        self.assertIs(cave.grid.at(Tile(13, 38)).behavior, Behavior.NONE)
        self.assertEqual([(w.tile, w.to_map) for w in cave.warps],
                         [(Tile(19, 50), "Route 204 South"), (Tile(28, 44), "Route 204 North")])
        self.assertIs(cave.grid.at(Tile(19, 51)).behavior, Behavior.DOOR)
        self.assertTrue(cave.grid.at(Tile(19, 30)).blocked)
        self.assertIs(cave.grid.at(Tile(15, 5)).behavior, Behavior.UNKNOWN)       # the part water cuts off

    def test_standing_npcs_are_walls_in_the_world(self):
        world = bdsp.story_world()
        self.assertTrue(world.at(Place("Route 202", Tile(6, 13))).blocked)
        self.assertTrue(world.at(Place("Route 201", Tile(44, 10))).blocked)
        self.assertFalse(bdsp.load_map("Route 202").grid.at(Tile(6, 13)).blocked)

    def test_wanderers_are_not_walls_in_the_world(self):
        world = bdsp.story_world()
        self.assertTrue(world.at(Place("Jubilife City", Tile(46, 35))).blocked)       # the Poketch president
        self.assertFalse(world.at(Place("Jubilife City", Tile(46, 21))).blocked)      # the green-haired man
        self.assertFalse(world.at(Place("Jubilife City", Tile(15, 18))).blocked)      # the Poketch clown


class StoryWorldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = bdsp.story_world()
        cls.data = load_wall_hits()

    def test_maps_join_where_their_exits_meet(self):
        for join in self.data["joins"]:
            start = WorldState(place(join["from"]))
            result = world_step(self.world, start, Direction.parse(join["direction"]))
            with self.subTest(join=join):
                self.assertEqual(result, Moved(WorldState(place(join["to"]))))

    def test_doors_warp_between_the_maps(self):
        for warp in self.data["warps"]:
            direction = Direction.parse(warp["direction"])
            result = world_step(self.world, WorldState(place(warp["from"])), direction)
            with self.subTest(warp=warp):
                self.assertEqual(result, Warped(WorldState(place(warp["to"])), direction))

    def test_measured_walks(self):
        for walk in self.data["walks"]:
            result = world_walk(self.world, WorldState(place(walk["from"])), Direction.parse(walk["direction"]))
            with self.subTest(walk=walk):
                self.assertEqual(result.state.place, place(walk["stop"]))
                self.assertEqual(result.tiles, walk["tiles"])
                self.assertEqual(result.held, walk["held"])

    def test_pending_walks_name_known_maps_and_say_why(self):
        for walk in self.data["pending"]:
            with self.subTest(walk=walk):
                self.assertIn(walk["from"][0], bdsp.MAP_FILES)
                self.assertTrue(walk["reason"])


if __name__ == "__main__":
    unittest.main()
