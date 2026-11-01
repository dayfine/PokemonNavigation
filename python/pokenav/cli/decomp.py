"""Generate map files from a Sinnoh decompilation checkout (pret/pokediamond
or pret/pokeplatinum).

pret data is not committed here, so the maps are read from a checkout on
disk (`pokenav.decomp.repos`), built by `pokenav.decomp.generate` and
written with the standard text legend (`maps.textgrid`). Cells are matrix
(row, col) pairs; world tile (x, z) is in cell (z // 32, x // 32).

Run from the repository root with PYTHONPATH=python:

    python3 -m pokenav.cli.decomp --repo ~/pokediamond --source pokediamond --game bdsp \
        --name "Route 201" --matrix 0 --cells 26,3 26,4 --events 327 \
        --out games/bdsp/maps/route_201.json
    wrote games/bdsp/maps/route_201.json (64 x 32), 1 walkable component

`--crop x0,z0,w,h` takes a world box instead of the cells' bounds;
`--component x,z` keeps only the walkable component holding that world tile
(one map, one connected component); `--keep old.json` carries a hand-edited
file's points, buildings, notes, status and NPC names over.
"""

import argparse
import sys
from typing import List, Optional, Tuple

from pokenav.decomp import generate as gen
from pokenav.decomp.generate import Selection
from pokenav.decomp.repos import REPOS, open_repo
from pokenav.grid.maps import schema, textgrid


def _ints(text: str, count: int) -> Tuple[int, ...]:
    values = tuple(int(v) for v in text.split(","))
    if len(values) != count:
        raise argparse.ArgumentTypeError("%r should be %d numbers separated by commas" % (text, count))
    return values


def run(args: argparse.Namespace) -> str:
    """Generates and writes the map; returns the line to print."""
    repo = open_repo(args.source, args.repo, args.commit)
    selection = Selection(args.matrix, [tuple(c) for c in args.cells], args.events, args.crop, args.component)
    map_file = gen.generate(repo, args.name, args.game, selection)
    if args.keep:
        gen.keep_records(map_file, schema.load(args.keep))
    schema.dump(args.out, map_file, textgrid.STANDARD.cells())
    components = gen.walkable_components(map_file.grid)
    sizes = "" if len(components) < 2 else " (%s tiles)" % ", ".join(str(len(c)) for c in components)
    return "wrote %s (%d x %d), %d walkable component%s%s" % (
        args.out, map_file.grid.width, map_file.grid.height, len(components),
        "" if len(components) == 1 else "s", sizes)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m pokenav.cli.decomp",
                                     description="Generate a map file from a Sinnoh decompilation.")
    parser.add_argument("--repo", required=True, help="path to the checkout")
    parser.add_argument("--source", required=True, choices=sorted(REPOS), help="which decompilation it is")
    parser.add_argument("--game", default="bdsp", help="the game the map is for (default bdsp)")
    parser.add_argument("--name", required=True, help="the map's name")
    parser.add_argument("--matrix", type=int, default=0, help="matrix number (default 0, the overworld)")
    parser.add_argument("--cells", nargs="+", required=True, type=lambda t: _ints(t, 2), metavar="ROW,COL")
    parser.add_argument("--events", nargs="*", default=[], help="events files: a stem (route_201) or narc number (327)")
    parser.add_argument("--crop", type=lambda t: _ints(t, 4), metavar="X0,Z0,W,H", help="world box to keep")
    parser.add_argument("--component", type=lambda t: _ints(t, 2), metavar="X,Z",
                        help="world tile whose walkable component is kept")
    parser.add_argument("--keep", help="a map file whose points, buildings, notes and status carry over")
    parser.add_argument("--commit", default="", help="the checkout's commit, if .git does not say")
    parser.add_argument("--out", required=True, help="the map file to write")
    args = parser.parse_args(argv)
    print(run(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
