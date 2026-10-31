"""Tests for the BDSP map files and pokenav.games.bdsp: every map loads,
named places have the cells their notes say, the maps join where their exits
meet, and every measured walk in games/bdsp/wall_hits.json ends where it was
measured to."""

import json
import unittest

from pokenav.games import bdsp
from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.model import Behavior
from pokenav.grid.maps.world import Place
from pokenav.grid.movement import Moved, WorldState, world_step, world_walk


def place(value) -> Place:
    name, x, y = value
    return Place(name, Tile(x, y))


def load_wall_hits():
    with open(bdsp.WALL_HITS) as f:
        return json.load(f)


class MapFilesTest(unittest.TestCase):
    def test_sizes(self):
        sizes = {
            "Route 201": (64, 20),
            "Sandgem Town": (34, 23),
            "Route 202": (36, 26),
            "Jubilife City": (64, 48),
        }
        for name, size in sizes.items():
            grid = bdsp.load_map(name).grid
            self.assertEqual((grid.width, grid.height), size, name)

    def test_named_places(self):
        route202 = bdsp.load_map("Route 202")
        self.assertIs(route202.grid.at(route202.point("CATCH_SPOT").tile).behavior, Behavior.TALL_GRASS)
        self.assertEqual([n.name for n in route202.npcs if n.sight],
                         ["trainer_c", "trainer_b", "trainer_a", "trainer_d"])
        sandgem = bdsp.load_map("Sandgem Town")
        for building in sandgem.buildings:
            self.assertIs(sandgem.grid.at(building.door).behavior, Behavior.DOOR, building.name)
        self.assertIs(sandgem.grid.at(sandgem.point("POKEMON_CENTER_SIGN").tile).behavior, Behavior.SIGN)
        jubilife = bdsp.load_map("Jubilife City")
        for building in jubilife.buildings:
            self.assertIs(jubilife.grid.at(building.door).behavior, Behavior.DOOR, building.name)
        self.assertEqual(len(jubilife.npcs), 7)
        self.assertEqual([n.name for n in jubilife.npcs if n.wander],
                         ["clown_poketch_company", "green_haired_man"])

    def test_standing_npcs_are_walls_in_the_world(self):
        world = bdsp.story_world()
        self.assertTrue(world.at(Place("Route 202", Tile(7, 11))).blocked)
        self.assertTrue(world.at(Place("Route 201", Tile(43, 3))).blocked)
        self.assertFalse(bdsp.load_map("Route 202").grid.at(Tile(7, 11)).blocked)

    def test_wanderers_are_not_walls_in_the_world(self):
        world = bdsp.jubilife_world()
        self.assertTrue(world.at(Place("Jubilife City", Tile(44, 26))).blocked)
        self.assertFalse(world.at(Place("Jubilife City", Tile(44, 16))).blocked)
        self.assertFalse(world.at(Place("Jubilife City", Tile(13, 13))).blocked)


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

    def test_measured_walks(self):
        for walk in self.data["walks"]:
            result = world_walk(self.world, WorldState(place(walk["from"])), Direction.parse(walk["direction"]))
            with self.subTest(walk=walk):
                self.assertEqual(result.state.place, place(walk["stop"]))
                self.assertEqual(result.tiles, walk["tiles"])
                self.assertEqual(result.held, walk["held"])


if __name__ == "__main__":
    unittest.main()
