"""Tests for pokenav.decomp.generate: map files from the tiny checkouts of
test_decomp_repos, from either repository."""

import tempfile
import unittest

from pokenav.decomp import generate as gen
from pokenav.decomp.generate import Selection, keep_records, restrict_to_component, walkable_components
from pokenav.decomp.repos import open_repo
from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps import textgrid
from pokenav.grid.maps.model import Behavior, Cell, GridMap2D
from pokenav.grid.maps.schema import Building, Connection, Encounter, MapFile, NamedPoint, Note, Npc, Wander, Warp

from tests.test_decomp_repos import write_diamond, write_platinum

TOWN = Selection(0, [(0, 0)], ["tiny_town"])
ROUTE = Selection(0, [(0, 1)], ["tiny_route"])
DOOR = Cell(blocked=True, behavior=Behavior.DOOR)


def platinum_town(root, selection=TOWN):
    write_platinum(root)
    return gen.generate(open_repo("pokeplatinum", root, "c668969"), "Tiny Town", "test", selection)


class GenerateTest(unittest.TestCase):
    def test_cells_from_the_land_data(self):
        with tempfile.TemporaryDirectory() as root:
            town = platinum_town(root)
        grid = town.grid
        self.assertEqual((grid.name, grid.width, grid.height), ("Tiny Town", 32, 32))
        self.assertEqual(grid.at(Tile(12, 9)), DOOR)
        self.assertEqual(grid.at(Tile(14, 14)).behavior, Behavior.TALL_GRASS)
        self.assertEqual(grid.at(Tile(13, 13)), Cell(blocked=True, behavior=Behavior.WATER))
        self.assertEqual(grid.at(Tile(15, 10)), Cell(behavior=Behavior.WARP))
        self.assertEqual(grid.at(Tile(12, 16)), Cell(blocked=True, behavior=Behavior.LEDGE_SOUTH))
        self.assertTrue(grid.at(Tile(0, 0)).blocked)
        self.assertEqual(town.encounters, {Encounter.GRASS, Encounter.WATER})
        self.assertEqual(town.game, "test")
        self.assertEqual(town.status, gen.GENERATED_STATUS)
        self.assertIn("pret/pokeplatinum@c668969: res/field/maps/data/map_data_001.bin", town.source)
        self.assertIn("res/field/events/events_tiny_town.json", town.source)
        self.assertEqual(town.notes[0].source, "pret/pokeplatinum@c668969")

    def test_objects(self):
        with tempfile.TemporaryDirectory() as root:
            town = platinum_town(root)
        self.assertEqual(town.grid.at(Tile(10, 10)), Cell(blocked=True, behavior=Behavior.SIGN))
        self.assertEqual(town.grid.at(Tile(14, 10)), Cell(blocked=True, behavior=Behavior.ROCK))
        self.assertEqual([s.name for s in town.signs], ["signboard", "sign_script_77"])
        self.assertEqual((town.signs[0].tile, town.signs[0].facing), (Tile(10, 10), Direction.NORTH))
        guard, kid, potion = town.npcs
        self.assertEqual(guard, Npc("guard", Tile(12, 12), Direction.SOUTH, 3, None, "YOUNGSTER, LOOK_SOUTH"))
        self.assertEqual(kid.wander, Wander(Tile(10, 10), Tile(12, 12)))
        self.assertIsNone(kid.facing)
        self.assertEqual((potion.name, potion.tile, potion.sight), ("potion", Tile(11, 15), 0))
        self.assertIn("item ball", potion.note)
        self.assertIn("FLAG_OBTAINED_POTION", potion.note)
        hidden = [n for n in town.notes if n.text.startswith("objects a story flag hides")]
        self.assertEqual(len(hidden), 1)
        self.assertIn("rival at (13, 15) (FLAG_HIDE_RIVAL)", hidden[0].text)
        self.assertNotIn("copy", hidden[0].text)       # the neighbour's copy is skipped
        self.assertEqual(town.warps, [Warp(Tile(12, 9), "Tiny House", 0)])

    def test_connections_from_the_matrix(self):
        with tempfile.TemporaryDirectory() as root:
            town = platinum_town(root)
            route = platinum_town(root, ROUTE)
        self.assertEqual(town.connections, [Connection(Direction.EAST, "Tiny Route", 0)])
        self.assertEqual(route.connections, [Connection(Direction.WEST, "Tiny Town", 0)])
        self.assertEqual(route.encounters, {Encounter.CAVE})
        texts = [n.text for n in route.notes]
        self.assertTrue(any(t.startswith("one-way blocks imported as plain ground at (1, 5)") for t in texts))
        self.assertTrue(any(t.startswith("two-tile ledges (jump twice) imported as ledges at (2, 5)") for t in texts))

    def test_a_crop_loads_the_cells_it_reaches_and_is_unknown_past_the_matrix(self):
        with tempfile.TemporaryDirectory() as root:
            cropped = platinum_town(root, TOWN._replace(crop=(8, 8, 30, 10)))
            far = platinum_town(root, TOWN._replace(crop=(30, 30, 4, 4)))
        grid = cropped.grid
        self.assertEqual((grid.width, grid.height), (30, 10))
        self.assertEqual(grid.at(Tile(4, 1)), DOOR)                       # world (12, 9)
        self.assertEqual(grid.at(Tile(24, 0)).behavior, Behavior.NONE)    # world (32, 8): Tiny Route, loaded too
        self.assertEqual(grid.at(Tile(29, 0)).behavior, Behavior.NONE)
        self.assertFalse(any("outside the generated cells" in n.text for n in cropped.notes))
        self.assertIn("map_data_002.bin", cropped.source)
        self.assertIn(Connection(Direction.EAST, "Tiny Route", -8), cropped.connections)
        self.assertEqual(far.grid.at(Tile(1, 1)).behavior, Behavior.NONE)      # world (31, 31): Tiny Town
        self.assertEqual(far.grid.at(Tile(2, 1)).behavior, Behavior.NONE)      # world (32, 31): Tiny Route
        self.assertEqual(far.grid.at(Tile(2, 2)).behavior, Behavior.UNKNOWN)   # world (32, 32): no matrix row
        self.assertTrue(any("8 tiles of the box" in n.text for n in far.notes))

    def test_missing_cell(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "no map in cell"):
                platinum_town(root, Selection(0, [(1, 0)]))

    def test_both_repositories_give_the_same_map(self):
        with tempfile.TemporaryDirectory() as root:
            platinum = platinum_town(root)
        with tempfile.TemporaryDirectory() as root:
            write_diamond(root)
            diamond = gen.generate(open_repo("pokediamond", root, "b623abe"), "Tiny Town", "test", Selection(0, [(0, 0)], ["10"]))
        self.assertEqual(textgrid.show(diamond.grid), textgrid.show(platinum.grid))
        self.assertEqual([(n.tile, n.facing, n.sight, n.wander) for n in diamond.npcs],
                         [(n.tile, n.facing, n.sight, n.wander) for n in platinum.npcs])
        self.assertEqual([n.name for n in diamond.npcs], ["boy1", "girl1", "monstarball"])
        self.assertEqual([(w.tile, w.to_map, w.to_warp) for w in diamond.warps], [(Tile(12, 9), "Tiny House", 0)])
        self.assertEqual([s.tile for s in diamond.signs], [s.tile for s in platinum.signs])
        self.assertIn("files/fielddata/land_data/land_data_release/narc_0001.bin", diamond.source)
        self.assertEqual(diamond.encounters, platinum.encounters)


#   A grid with two rooms joined by a ledge (8 tiles), a room with a tile
#   behind a rock (5) and a corridor on its own (4).
ROOMS = textgrid.parse("""
// Map: rooms
#########
#..#..#.#
#..#..#.#
#vv#R##.#
#..#.##.#
#..######
#########
""").grid


class ComponentsTest(unittest.TestCase):
    def test_steps_ledges_and_rocks_join_tiles(self):
        components = walkable_components(ROOMS)
        self.assertEqual([len(c) for c in components], [8, 5, 4])
        self.assertIn(Tile(1, 1), components[0])
        self.assertIn(Tile(1, 5), components[0])        # over the ledge
        self.assertIn(Tile(4, 1), components[1])
        self.assertIn(Tile(4, 4), components[1])        # past the rock
        self.assertIn(Tile(7, 1), components[2])

    def test_restrict_turns_the_rest_unknown_and_drops_unreached_connections(self):
        map_file = MapFile(GridMap2D("rooms", ROOMS.rows()), connections=[
            Connection(Direction.NORTH, "A", 0), Connection(Direction.WEST, "B", 0)])
        map_file.grid.set(Tile(1, 0), Cell())            # the top room reaches the north edge
        changed = restrict_to_component(map_file, Tile(2, 5))
        self.assertEqual(changed, 9)
        self.assertEqual(map_file.grid.at(Tile(4, 1)).behavior, Behavior.UNKNOWN)
        self.assertEqual(map_file.grid.at(Tile(2, 5)), Cell())
        self.assertEqual(map_file.grid.at(Tile(1, 0)), Cell())
        self.assertEqual([c.map for c in map_file.connections], ["A"])
        self.assertIn("9 walkable tiles", map_file.notes[-1].text)
        with self.assertRaises(ValueError):
            restrict_to_component(map_file, Tile(0, 0))

    def test_restrict_to_a_single_component_changes_nothing(self):
        single = MapFile(textgrid.parse("#...#\n").grid)
        self.assertEqual(restrict_to_component(single, Tile(1, 0)), 0)
        self.assertEqual(single.notes, [])


class KeepRecordsTest(unittest.TestCase):
    def test_carries_hand_records_over(self):
        grid = GridMap2D("t", [[Cell(), Cell(), Cell()]])
        generated = MapFile(grid, status=gen.GENERATED_STATUS,
                            npcs=[Npc("boy1", Tile(0, 0), Direction.SOUTH, 3, note="BOY1, LOOK_SOUTH")],
                            notes=[Note("generated", "pret/pokediamond@b623abe"), Note("one-way", "decomp")])
        kept = MapFile(GridMap2D("t", [[Cell()]]), status="checked on the console",
                       points=[NamedPoint("START", Tile(1, 0), "a corner")],
                       buildings=[Building("Mart", "mart", Tile(2, 0))],
                       npcs=[Npc("trainer_a", Tile(0, 0), Direction.SOUTH, 4, note="holds the player"),
                             Npc("clown", Tile(2, 0), note="placed from the console")],
                       notes=[Note("old generated", "pret/pokeplatinum@c668969"), Note("measured", "console"),
                              Note("old component", "generator")])
        keep_records(generated, kept)
        self.assertEqual(generated.points, kept.points)
        self.assertEqual(generated.buildings, kept.buildings)
        self.assertEqual(generated.status, "checked on the console")
        self.assertEqual([(n.name, n.sight, n.note) for n in generated.npcs],
                         [("trainer_a", 3, "BOY1, LOOK_SOUTH. holds the player"), ("clown", 0, "placed from the console")])
        self.assertEqual([n.text for n in generated.notes], ["generated", "one-way", "measured"])

    def test_keeping_a_regenerated_file_changes_nothing(self):
        def generated():
            return MapFile(GridMap2D("t", [[Cell(), Cell()]]), status=gen.GENERATED_STATUS,
                           npcs=[Npc("boy1", Tile(0, 0), note="BOY1, LOOK_SOUTH"), Npc("potion", Tile(1, 0), note="item ball")],
                           notes=[Note("generated", "pret/pokediamond@b623abe")])
        once = keep_records(generated(), MapFile(GridMap2D("t", [[Cell()]]), npcs=[
            Npc("trainer_a", Tile(0, 0), note="holds the player")], notes=[Note("a difference", "pret/pokediamond vs pret/pokeplatinum")]))
        twice = keep_records(generated(), once)
        self.assertEqual(twice, once)
        self.assertEqual(twice.npcs[0].note, "BOY1, LOOK_SOUTH. holds the player")
        self.assertEqual(twice.npcs[1].note, "item ball")
        self.assertEqual([n.text for n in twice.notes], ["generated", "a difference"])


if __name__ == "__main__":
    unittest.main()
