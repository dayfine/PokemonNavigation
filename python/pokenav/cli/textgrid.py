"""Show a map as a text grid, or convert between text grids and map files.

The format and legend are in `pokenav.maps.textgrid`. A path ending in .json
is a map file (`maps.schema`); any other path is a text grid.

Run from the repository root with PYTHONPATH=python:

    python3 -m pokenav.cli.textgrid show docs/examples/tiny_town.json
    // Map: Tiny Town
    //   DOORSTEP 1 1
    #D#  // 0
    #N#  // 1
    // Elevation:
    // 333
    // 333

    python3 -m pokenav.cli.textgrid convert route.txt route.json   # text -> map file
    python3 -m pokenav.cli.textgrid convert route.json route.txt   # map file -> text
"""

import argparse
import sys
from typing import List, Optional

from pokenav.maps import schema, textgrid
from pokenav.maps.schema import MapFile


def load_any(path: str) -> MapFile:
    """A map file from `path`: read as JSON if it ends in .json, else parsed
    as a text grid."""
    if path.endswith(".json"):
        return schema.load(path)
    with open(path, encoding="utf-8") as f:
        return textgrid.parse(f.read())


def save_any(path: str, map_file: MapFile) -> None:
    """Writes `map_file` to `path`: as JSON if it ends in .json, else as a
    text grid."""
    if path.endswith(".json"):
        schema.dump(path, map_file, textgrid.STANDARD.cells())
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(textgrid.serialize(map_file))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m pokenav.cli.textgrid",
                                     description="Show or convert maps between text grids and map files.")
    commands = parser.add_subparsers(dest="command", required=True)
    show_cmd = commands.add_parser("show", help="print a map file or text grid as text")
    show_cmd.add_argument("path")
    convert = commands.add_parser("convert", help="text grid <-> map file, by extension (.json is a map file)")
    convert.add_argument("source")
    convert.add_argument("target")
    args = parser.parse_args(argv)

    if args.command == "show":
        sys.stdout.write(textgrid.serialize(load_any(args.path)))
    else:
        save_any(args.target, load_any(args.source))
    return 0


if __name__ == "__main__":
    sys.exit(main())
