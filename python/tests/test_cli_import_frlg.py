"""Tests for pokenav.cli.import_frlg: writing map files from a checkout."""

import os
import struct
import tempfile
import unittest

from pokenav.cli.import_frlg import import_maps
from pokenav.maps import schema
from pokenav.maps.pret import Checkout

from tests.test_maps_pret import LEDGE, TINY_BLOCKS, TINY_GAME, block, write_fixture

#   The pret test's blocks with its ledges blocked, as FRLG's are, so every
#   cell has a character in the standard legend that map files are written
#   with.
BLOCKED_LEDGE = block(LEDGE, 1, 0)
TINY_BLOCKS_WITH_BLOCKED_LEDGES = [
    [BLOCKED_LEDGE if b == block(LEDGE, 0, 0) else b for b in row] for row in TINY_BLOCKS
]


class ImportMapsTest(unittest.TestCase):
    def test_writes_one_file_per_map(self):
        with tempfile.TemporaryDirectory() as root:
            write_fixture(root)
            blocks = [b for row in TINY_BLOCKS_WITH_BLOCKED_LEDGES for b in row]
            with open(os.path.join(root, "data/layouts/Tiny/map.bin"), "wb") as f:
                f.write(struct.pack("<%dH" % len(blocks), *blocks))
            checkout = Checkout(root, TINY_GAME)
            out = os.path.join(root, "out")

            lines = import_maps(checkout, ["TinyTown", "TinyHouse"], out)

            self.assertEqual(lines, [
                "wrote %s (4 x 3)" % os.path.join(out, "TinyTown.json"),
                "wrote %s (4 x 3)" % os.path.join(out, "TinyHouse.json"),
            ])
            town = schema.load(os.path.join(out, "TinyTown.json"))
            self.assertEqual(town.grid, checkout.load_map("TinyTown").grid)


if __name__ == "__main__":
    unittest.main()
