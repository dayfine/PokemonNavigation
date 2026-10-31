"""Tests for pokenav.physics.params and pokenav.physics.model: the file
format, unknown and missing names, the error model's rounding, and the BDSP
and FRLG physics files."""

import unittest

from pokenav.games import bdsp, frlg
from pokenav.physics import params
from pokenav.physics.model import Mode, TileError, from_params

#   Where the BDSP values marked measured come from.
BDSP_SOURCE = "games/bdsp/MEASUREMENTS.md results 2026-10-31"

#   A complete foot-only file.
FOOT_ONLY = """\
# name                value  status    source
foot.tile_cost        1      defined   the unit
foot.dpad.per_tile    0      measured  a record (#2)
foot.dpad.overshoot   0      measured  a record
foot.stick.per_tile   0.15   measured  a record
foot.stick.overshoot  0      measured  a record
turn_tap              1      guessed   to measure: taps
mount                 0      guessed   no bike
door                  8      guessed   to measure: the fade
"""


class ParamsTest(unittest.TestCase):
    def test_parse_keeps_status_and_source(self):
        parsed = params.parse(FOOT_ONLY)
        self.assertEqual(parsed["foot.stick.per_tile"], params.Param(0.15, "measured", "a record"))
        self.assertEqual(parsed["foot.dpad.per_tile"].source, "a record (#2)")

    def test_bad_lines(self):
        for text in ("turn_tap 1 measured", "turn_tap one measured x", "turn_tap 1 hoped x",
                     "turn_tap 1 guessed x\nturn_tap 2 guessed y"):
            with self.assertRaises(ValueError, msg=text):
                params.parse(text)


class ModelTest(unittest.TestCase):
    def test_foot_only_file_has_no_bike(self):
        model = from_params(params.parse(FOOT_ONLY))
        self.assertIsNone(model.bike)
        self.assertIsNone(model.mode(Mode.BIKE))
        self.assertEqual(model.foot.stick, TileError(0.15, 0.0))

    def test_unknown_and_missing_names(self):
        with self.assertRaisesRegex(ValueError, "unknown.*foot.speed"):
            from_params(params.parse(FOOT_ONLY + "foot.speed 2 guessed x\n"))
        with self.assertRaisesRegex(ValueError, "missing.*door"):
            from_params(params.parse(FOOT_ONLY.replace("door ", "#door ")))

    def test_spread_rounds_to_whole_tiles(self):
        stick = TileError(per_tile=0.15)
        #   Under half a tile up to 11 tiles; 18 tiles comes to about 0.64.
        self.assertEqual([stick.spread(n) for n in (1, 11, 12, 18, 20)], [0, 0, 1, 1, 1])
        self.assertEqual(TileError().spread(99), 0)
        self.assertEqual(TileError(overshoot=1.0).spread(1), 1)


class GameFilesTest(unittest.TestCase):
    def test_bdsp_taps_are_exact_and_stick_holds_are_not(self):
        model = bdsp.execution_model()
        self.assertEqual(model.foot.dpad.spread(22), 0)
        self.assertEqual(model.foot.stick.spread(20), 1)
        self.assertIsNotNone(model.bike)

    def test_bdsp_measured_values_name_the_results(self):
        for name, param in params.load(bdsp.PHYSICS).items():
            if param.status == "measured":
                self.assertTrue(param.source.startswith(BDSP_SOURCE), name)
            if name.startswith("bike."):
                self.assertEqual(param.status, "guessed", name)
                self.assertIn("to measure", param.source, name)

    def test_frlg_is_grid_locked_with_a_faster_bike(self):
        model = frlg.execution_model()
        for mode in Mode:
            self.assertEqual(model.mode(mode).dpad.spread(99), 0)
            self.assertEqual(model.mode(mode).stick.spread(99), 0)
        self.assertLess(model.bike.tile_cost, model.foot.tile_cost)
        loaded = params.load(frlg.PHYSICS)
        self.assertEqual(loaded["bike.tile_cost"].status, "pret")


if __name__ == "__main__":
    unittest.main()
