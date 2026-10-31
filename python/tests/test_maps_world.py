"""Tests for pokenav.grid.maps.world and stepping across maps with
pokenav.grid.movement.world_step: connections with offsets, and a door pair."""

import unittest

from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.schema import Connection, MapFile, Warp
from pokenav.grid.maps.textgrid import parse
from pokenav.grid.maps.world import Arrival, Place, World
from pokenav.grid.movement import (
    Blocked, BlockReason, Edge, Moved, Warped, WorldState, world_step, world_walk,
)

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST


def map_file(name, text, connections=(), warps=()):
    grid = parse(text, name=name).grid
    return MapFile(grid, connections=list(connections), warps=list(warps))


def two_towns() -> World:
    """North (5 x 3) sits above South (3 x 3), shifted one tile east of it:
    North's x is South's x + 1. Side (2 x 2) is east of North, one row down.
    South has a door at (1, 1) into House, whose exit mat is at (1, 2).
    North's west edge leads to Far, which is not loaded."""
    north = map_file("North", ".....\n.....\n.....\n", [
        Connection(S, "South", 1), Connection(E, "Side", 1), Connection(W, "Far", 0)])
    south = map_file("South", "...\n.D.\n...\n", [Connection(N, "North", -1)],
                     [Warp(Tile(1, 1), "House", 0)])
    side = map_file("Side", "..\n..\n", [Connection(W, "North", -1)])
    house = map_file("House", "###\n#.#\n#W#\n", warps=[Warp(Tile(1, 2), "South", 0)])
    return World([north, south, side, house])


def at(name, x, y, elevation=0):
    return WorldState(Place(name, Tile(x, y)), elevation)


class WorldTest(unittest.TestCase):
    def test_across_each_edge(self):
        world = two_towns()
        cases = {
            Place("North", Tile(2, 3)): Place("South", Tile(1, 0)),
            Place("South", Tile(0, -1)): Place("North", Tile(1, 2)),
            Place("North", Tile(5, 1)): Place("Side", Tile(0, 0)),
            Place("Side", Tile(-1, 1)): Place("North", Tile(4, 2)),
        }
        for beyond, expected in cases.items():
            self.assertEqual(world.across_edge(beyond), expected, beyond)

    def test_no_connection_there(self):
        world = two_towns()
        self.assertIsNone(world.connection_at(Place("North", Tile(0, 3))))   # west of South
        self.assertIsNone(world.across_edge(Place("North", Tile(2, -1))))   # no north connection
        self.assertIsNone(world.connection_at(Place("North", Tile(2, 2))))  # on the map
        self.assertEqual(world.connection_at(Place("North", Tile(-1, 0))).map, "Far")
        self.assertIsNone(world.across_edge(Place("North", Tile(-1, 0))))   # Far is not loaded

    def test_warp_arrivals(self):
        world = two_towns()
        #   Into the house: arrive on its exit mat, facing the way we walked.
        self.assertEqual(world.warp_arrival(Place("South", Tile(1, 1)), N),
                         Arrival(Place("House", Tile(1, 2)), N))
        #   Out of the house: arrive at the door and step out of it, south.
        self.assertEqual(world.warp_arrival(Place("House", Tile(1, 2)), S),
                         Arrival(Place("South", Tile(1, 2)), S))
        self.assertIsNone(world.warp_arrival(Place("South", Tile(0, 0)), N))

    def test_bad_warp_index_and_duplicate_maps(self):
        world = World([map_file("A", "W\n", warps=[Warp(Tile(0, 0), "B", 3)]),
                       map_file("B", ".\n")])
        with self.assertRaises(ValueError):
            world.warp_arrival(Place("A", Tile(0, 0)), N)
        with self.assertRaises(ValueError):
            world.add(map_file("A", ".\n"))


class WorldStepTest(unittest.TestCase):
    def test_steps(self):
        world = two_towns()
        cases = [
            (at("North", 2, 2), S, Moved(at("South", 1, 0))),
            (at("North", 0, 2), S, Blocked(BlockReason.WALL)),     # past South's west side
            (at("North", 2, 0), N, Blocked(BlockReason.WALL)),     # no connection north
            (at("North", 0, 0), W, Edge(W)),                       # to Far, not loaded
            (at("North", 4, 0), E, Blocked(BlockReason.WALL)),     # above Side
            (at("North", 4, 1), E, Moved(at("Side", 0, 0))),
            (at("South", 1, 2), N, Warped(at("House", 1, 2), N)),
            (at("House", 1, 1), S, Warped(at("South", 1, 2), S)),
            (at("North", 1, 1), E, Moved(at("North", 2, 1))),
        ]
        for state, direction, expected in cases:
            with self.subTest(state=state, direction=direction):
                self.assertEqual(world_step(world, state, direction), expected)

    def test_objects_and_elevation_across_an_edge(self):
        world = World([
            map_file("Low", "..\n", [Connection(E, "High", 0)]),
            map_file("High", "..\n// Elevation:\n// 33\n", [Connection(W, "Low", 0)]),
        ])
        self.assertEqual(world_step(world, at("Low", 1, 0), E), Blocked(BlockReason.ELEVATION))
        self.assertEqual(world_step(world, at("Low", 1, 0, 3), E), Moved(at("High", 0, 0, 3)))
        self.assertEqual(world_step(world, at("Low", 1, 0, 3), E, objects={Place("High", Tile(0, 0))}),
                         Blocked(BlockReason.OBJECT))

    def test_walk_across_an_edge_to_a_door(self):
        world = two_towns()
        walked = world_walk(world, at("North", 2, 0), S)
        self.assertEqual((walked.state, walked.tiles), (at("South", 1, 0), 3))
        self.assertEqual(walked.stop, Warped(at("House", 1, 2), S))
        self.assertFalse(walked.held)

    def test_walk_to_a_wall_across_maps(self):
        walked = world_walk(two_towns(), at("Side", 1, 0), W)
        self.assertEqual((walked.state, walked.tiles, walked.held), (at("North", 0, 1), 6, False))
        self.assertEqual(walked.stop, Edge(W))


if __name__ == "__main__":
    unittest.main()
