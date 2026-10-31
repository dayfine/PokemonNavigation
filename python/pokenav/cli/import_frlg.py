"""Import FRLG maps from a local pokefirered checkout into map files.

pret data is not committed here, so the maps are read from a checkout on
disk with the FRLG numbers in `pokenav.games.frlg`, and each is written as
<map>.json with the standard text legend (`maps.textgrid`).

Run from the repository root with PYTHONPATH=python:

    python3 -m pokenav.cli.import_frlg ~/pokefirered Route1 PalletTown --out /tmp/frlg
    wrote /tmp/frlg/Route1.json (24 x 40)
    wrote /tmp/frlg/PalletTown.json (24 x 20)
"""

import argparse
import os
import sys
from typing import List, Optional, Sequence

from pokenav.games import frlg
from pokenav.grid.maps import schema, textgrid
from pokenav.grid.maps.pret import Checkout


def import_maps(checkout: Checkout, names: Sequence[str], out_dir: str) -> List[str]:
    """Writes each named map of `checkout` to `out_dir`/<name>.json and
    returns one "wrote <path> (<width> x <height>)" line per map."""
    os.makedirs(out_dir, exist_ok=True)
    lines = []
    for name in names:
        map_file = checkout.load_map(name)
        path = os.path.join(out_dir, name + ".json")
        schema.dump(path, map_file, textgrid.STANDARD.cells())
        lines.append("wrote %s (%d x %d)" % (path, map_file.grid.width, map_file.grid.height))
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m pokenav.cli.import_frlg",
                                     description="Import FRLG maps from a pokefirered checkout.")
    parser.add_argument("checkout", help="path to a pokefirered checkout")
    parser.add_argument("maps", nargs="+", help="map names, as in data/maps/ (Route1)")
    parser.add_argument("--out", default=".", help="directory to write <map>.json files to")
    args = parser.parse_args(argv)

    for line in import_maps(Checkout(args.checkout, frlg.PRET), args.maps, args.out):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
