"""Tests for pokenav.grid.maps.schema: reading and writing JSON map files."""

import json
import os
import tempfile
import unittest

from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps import schema
from pokenav.grid.maps.model import OPEN, WALL, Behavior, Cell, GridMap2D
from pokenav.grid.maps.schema import Encounter, MapFile, MapImage, Npc, Wander, wild_battle_possible

from tests.paths import DOCS_EXAMPLES

TINY_TOWN = os.path.join(DOCS_EXAMPLES, "tiny_town.json")

#   The legend tiny_town.json uses.
DOOR = Cell(blocked=True, behavior=Behavior.DOOR)
LEGEND = {"#": WALL, ".": OPEN, "D": DOOR}
#   Legend entries for tall grass and water, as map files write them.
GRASS_LEGEND = {".": {}, '"': {"behavior": "tall_grass"}}
WATER_LEGEND = {"~": {"blocked": True, "behavior": "water"}}


def minimal(rows, legend=None, **extra):
    """The parsed form of a map file with only the required keys."""
    data = {
        "format": schema.FORMAT,
        "name": "test",
        "legend": legend or {"#": {"blocked": True}, ".": {}},
        "rows": rows,
    }
    data.update(extra)
    return data


class LoadTest(unittest.TestCase):
    def test_the_documented_example(self):
        town = schema.load(TINY_TOWN)
        self.assertEqual((town.name, town.game), ("Tiny Town", "example"))
        self.assertEqual((town.grid.width, town.grid.height), (3, 2))
        self.assertEqual(town.grid.at(Tile(1, 0)), DOOR._replace(elevation=3))
        self.assertEqual(town.grid.at(Tile(1, 1)), Cell(elevation=3))
        self.assertEqual(town.point("DOORSTEP").tile, Tile(1, 1))
        self.assertEqual(town.npcs, [Npc("guard", Tile(1, 1), Direction.SOUTH, sight=3)])
        self.assertIs(town.signs[0].facing, Direction.NORTH)
        self.assertEqual(town.buildings[0].door, Tile(1, 0))
        self.assertEqual((town.warps[0].to_map, town.warps[0].to_warp), ("Tiny Mart", 0))
        self.assertEqual(town.connections[0].offset, -4)
        self.assertEqual(town.notes[0].source, "console")
        self.assertEqual((town.source, town.status), ("drawn for the docs", "example only"))
        self.assertEqual(town.image, MapImage("tiny_town.png", 8, 0, 16))
        self.assertEqual(town.encounters, frozenset())

    def test_only_the_cells_are_required(self):
        town = schema.from_json(minimal(["#.", ".#"]))
        self.assertEqual(town.grid.rows(), [[WALL, OPEN], [OPEN, WALL]])
        self.assertEqual((town.points, town.npcs, town.game), ([], [], ""))
        self.assertEqual((town.source, town.status), ("", ""))
        self.assertEqual(town.encounters, frozenset())
        with self.assertRaises(KeyError):
            town.point("NOWHERE")

    def test_wanderers(self):
        data = minimal(["..."], npcs=[{"name": "kid", "tile": [1, 0],
                                       "wander": {"low": [0, 0], "high": [2, 0], "rate": 0.5}}])
        kid = schema.from_json(data).npcs[0]
        self.assertEqual(kid.wander, Wander(Tile(0, 0), Tile(2, 0), 0.5))
        self.assertIsNone(kid.facing)

    def test_errors(self):
        bad = {
            "wrong format": dict(minimal(["."]), format="other/1"),
            "unknown character": minimal([".x"]),
            "ragged rows": minimal(["..", "."]),
            "elevation row count": minimal([".."], elevation=["00", "00"]),
            "elevation row width": minimal([".."], elevation=["0"]),
            "elevation digit": minimal([".."], elevation=["0G"]),
            "unknown behavior": minimal(["."], legend={".": {"behavior": "lava"}}),
            "legend key": minimal(["."], legend={"..": {}}),
            "unknown encounter": minimal(["."], encounters=["lava"]),
            "grass not listed": minimal(['."'], legend=GRASS_LEGEND, encounters=[]),
            "water not listed": minimal(["~"], legend=WATER_LEGEND, encounters=["grass"]),
        }
        for name, data in bad.items():
            with self.assertRaises(ValueError, msg=name):
                schema.from_json(data)

    def test_load_names_the_file_in_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w") as f:
                json.dump(minimal([".x"]), f)
            with self.assertRaisesRegex(ValueError, "bad.json"):
                schema.load(path)


class EncountersTest(unittest.TestCase):
    #   A route: open ground, tall grass, a pond and a wall.
    ROUTE = minimal(['.\"~#'], legend=dict(GRASS_LEGEND, **WATER_LEGEND, **{"#": {"blocked": True}}),
                    encounters=["grass", "water"])

    def test_route_battles_only_on_grass_and_water(self):
        route = schema.from_json(self.ROUTE)
        self.assertEqual(route.encounters, {Encounter.GRASS, Encounter.WATER})
        possible = [wild_battle_possible(route, Tile(x, 0)) for x in range(4)]
        self.assertEqual(possible, [False, True, True, False])

    def test_town_has_none(self):
        town = schema.load(TINY_TOWN)
        self.assertFalse(any(wild_battle_possible(town, tile) for tile in town.grid.tiles()))

    def test_cave_battles_on_every_walkable_tile(self):
        cave = schema.from_json(minimal(["#.."], encounters=["cave"]))
        possible = [wild_battle_possible(cave, Tile(x, 0)) for x in range(3)]
        self.assertEqual(possible, [False, True, True])

    def test_a_file_without_the_key_gets_what_its_cells_imply(self):
        plain = schema.from_json(minimal([".."]))
        self.assertEqual(plain.encounters, frozenset())
        self.assertIs(wild_battle_possible(plain, Tile(0, 0)), False)
        route = schema.from_json(minimal(['."~'], legend=dict(GRASS_LEGEND, **WATER_LEGEND)))
        self.assertEqual(route.encounters, {Encounter.GRASS, Encounter.WATER})
        self.assertEqual(schema.implied_encounters(route.grid), route.encounters)

    def test_unknown_when_the_map_is_built_without_saying_or_off_the_map(self):
        plain = MapFile(GridMap2D("plain", [[OPEN]]))
        self.assertIsNone(wild_battle_possible(plain, Tile(0, 0)))
        cave = schema.from_json(minimal([".."], encounters=["cave"]))
        self.assertIsNone(wild_battle_possible(cave, Tile(5, 0)))

    def test_round_trip(self):
        route = schema.from_json(self.ROUTE)
        legend = {".": OPEN, '"': Cell(behavior=Behavior.TALL_GRASS),
                  "~": Cell(blocked=True, behavior=Behavior.WATER), "#": WALL}
        self.assertEqual(schema.to_json(route, legend)["encounters"], ["grass", "water"])
        self.assertEqual(schema.loads(schema.dumps(route, legend)), route)


class DumpTest(unittest.TestCase):
    def test_round_trip_of_the_example(self):
        with open(TINY_TOWN) as f:
            original = json.load(f)
        town = schema.loads(json.dumps(original))
        self.assertEqual(schema.to_json(town, LEGEND), original)
        self.assertEqual(schema.loads(schema.dumps(town, LEGEND)), town)

    def test_writes_only_what_is_set(self):
        grid = GridMap2D("plain", [[WALL, OPEN]])
        data = schema.to_json(MapFile(grid), LEGEND)
        self.assertEqual(data, {
            "format": schema.FORMAT,
            "name": "plain",
            "legend": {"#": {"blocked": True}, ".": {}},
            "rows": ["#."],
        })

    def test_source_status_and_rock_round_trip(self):
        legend = {"#": WALL, ".": OPEN, "R": Cell(blocked=True, behavior=Behavior.ROCK)}
        data = minimal([".R#"], legend={"#": {"blocked": True}, ".": {}, "R": {"blocked": True, "behavior": "rock"}},
                       source="pret/pokediamond", status="console checks pending")
        cave = schema.from_json(data)
        self.assertEqual((cave.source, cave.status), ("pret/pokediamond", "console checks pending"))
        self.assertEqual(cave.grid.at(Tile(1, 0)), Cell(blocked=True, behavior=Behavior.ROCK))
        written = schema.to_json(cave, legend)
        self.assertEqual((written["source"], written["status"]), ("pret/pokediamond", "console checks pending"))
        self.assertEqual(schema.loads(schema.dumps(cave, legend)), cave)

    def test_cell_without_a_character(self):
        grid = GridMap2D("pond", [[Cell(blocked=True, behavior=Behavior.WATER)]])
        with self.assertRaisesRegex(ValueError, "no legend character"):
            schema.dumps(MapFile(grid), LEGEND)

    def test_dump_and_load_a_file(self):
        town = schema.load(TINY_TOWN)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "town.json")
            schema.dump(path, town, LEGEND)
            self.assertEqual(schema.load(path), town)


if __name__ == "__main__":
    unittest.main()
