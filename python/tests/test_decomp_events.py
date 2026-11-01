"""Tests for pokenav.decomp.events: objects, warps and signs from Platinum's
JSON and Diamond's binary records."""

import unittest

from pokenav.decomp import events
from pokenav.decomp.events import Kind, ObjectEvent, SignEvent, WarpEvent, facing_of
from pokenav.grid.geometry import Direction

from tests.test_decomp_repos import DP_OBJECTS, PT_EVENTS, dp_events_bytes

N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST

DP_SPRITES = {3: "BOY1", 6: "GIRL1", 93: "SIGNBOARD", 85: "BREAKROCK", 87: "MONSTARBALL", 148: "RIVEL"}
DP_MAPS = {3: "MAP_TINY_HOUSE"}


class FacingTest(unittest.TestCase):
    def test_look_movements_face_their_first_direction(self):
        self.assertIs(facing_of("LOOK_SOUTH", 0), S)
        self.assertIs(facing_of("LOOK_SOUTH_AND_EAST", 0), S)
        self.assertIs(facing_of("LOOK_NORTH_WEST_AND_EAST", 1), N)
        self.assertIs(facing_of("LOOK_WEST_AND_EAST", 1), W)

    def test_others_use_the_initial_direction_and_wanderers_none(self):
        self.assertIs(facing_of("NONE", 3), E)
        self.assertIs(facing_of("LOOK_AROUND", 2), W)
        self.assertIsNone(facing_of("NONE", None))
        self.assertIsNone(facing_of("WANDER_AROUND", 1))
        self.assertIsNone(facing_of("WALK_BACK_AND_FORTH", 1))


class JsonTest(unittest.TestCase):
    def test_objects(self):
        parsed = events.events_from_json(PT_EVENTS)
        guard, kid, sign, rock, potion, rival, copy = parsed.objects
        self.assertEqual(guard, ObjectEvent("guard", "YOUNGSTER", "LOOK_SOUTH", 12, 12, S, 0, 0, sight=3))
        self.assertEqual((kid.movement, kid.facing, kid.range_x, kid.range_z, kid.sight), ("WANDER_AROUND", None, 1, 1, 0))
        self.assertTrue(kid.wanders)
        self.assertFalse(guard.wanders)
        self.assertEqual([o.kind for o in parsed.objects],
                         [Kind.PERSON, Kind.PERSON, Kind.SIGN, Kind.ROCK, Kind.ITEM, Kind.PERSON, Kind.PERSON])
        self.assertEqual((potion.hidden, rival.hidden, copy.hidden, guard.hidden),
                         ("FLAG_OBTAINED_POTION", "FLAG_HIDE_RIVAL", "MAP_HEADER_TINY_ROUTE", ""))
        self.assertIs(rival.facing, S)

    def test_trainer_without_a_range_sees_the_default(self):
        data = dict(PT_EVENTS["object_events"][0], data=[])
        self.assertEqual(events.events_from_json({"object_events": [data]}).objects[0].sight, events.DEFAULT_SIGHT)

    def test_warps_and_signs(self):
        parsed = events.events_from_json(PT_EVENTS)
        self.assertEqual(parsed.warps, [WarpEvent(12, 9, "MAP_HEADER_TINY_HOUSE", 0)])
        self.assertEqual(parsed.signs, [SignEvent(15, 15, 77)])      # the type 2 hidden item is not a sign

    def test_an_object_without_an_id_is_numbered(self):
        data = {k: v for k, v in PT_EVENTS["object_events"][0].items() if k != "id"}
        self.assertEqual(events.events_from_json({"object_events": [data]}).objects[0].name, "object_0")


class BinaryTest(unittest.TestCase):
    def test_reads_the_same_records_as_the_json(self):
        parsed = events.events_from_binary(dp_events_bytes(), DP_SPRITES, DP_MAPS)
        json_objects = events.events_from_json(PT_EVENTS).objects[:6]
        for binary, json_object in zip(parsed.objects, json_objects):
            with self.subTest(json_object.name):
                self.assertEqual((binary.x, binary.z, binary.movement, binary.facing, binary.range_x,
                                  binary.range_z, binary.sight, binary.kind),
                                 (json_object.x, json_object.z, json_object.movement, json_object.facing,
                                  json_object.range_x, json_object.range_z, json_object.sight, json_object.kind))
        self.assertEqual([o.name for o in parsed.objects], ["boy1", "girl1", "signboard", "breakrock", "monstarball", "rivel"])
        self.assertEqual([o.hidden for o in parsed.objects], ["", "", "", "", "flag 500", "flag 400"])
        self.assertEqual(parsed.warps, [WarpEvent(12, 9, "MAP_TINY_HOUSE", 0)])
        self.assertEqual(parsed.signs, [SignEvent(15, 15, 77)])

    def test_unknown_numbers_keep_their_values(self):
        record = (0, 200, 60, 1, 0, 0, 0, (0, 0, 0), 0, 0, 1, 2, 0)
        parsed = events.events_from_binary(dp_events_bytes([record], ((1, 1, 9, 2),), ((5, 0, 1, 1),), 0), {}, {})
        obj = parsed.objects[0]
        self.assertEqual((obj.graphic, obj.movement, obj.sight), ("SPRITE_200", "MOVEMENT_60", events.DEFAULT_SIGHT))
        self.assertEqual(parsed.warps[0].to_map, "MAP_9")
        self.assertEqual(parsed.signs, [SignEvent(1, 1, 5)])         # a type 0 sign, read facing it

    def test_rejects_a_file_of_the_wrong_length(self):
        with self.assertRaisesRegex(ValueError, "bytes read"):
            events.events_from_binary(dp_events_bytes() + b"\0\0", DP_SPRITES, DP_MAPS)


if __name__ == "__main__":
    unittest.main()
