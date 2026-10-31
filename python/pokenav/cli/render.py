"""Draw a route and regions over a map, as text or as a PNG.

The drawing is `pokenav.maps.render`. `--path` takes waypoints x,y; each
consecutive pair is one straight leg. Each `--region` is a set of tiles (a
belief set). With `--out` the result is a picture: the map's own image if
`--image` is given (lined up by the map file's `image` entry), else flat
colors per cell.

Run from the repository root with PYTHONPATH=python:

    python3 -m pokenav.cli.render games/bdsp/maps/route_202.json \\
        --path 19,22 30,22 30,19 --region 29,19 30,19
    ...
    ###,,,,,,......,,,,,,..o*X.....#####   // row 19: the region, the path, the end
    ...

    python3 -m pokenav.cli.render games/bdsp/maps/route_202.json \\
        --path 19,22 30,22 30,19 --image ~/maps/Route_202_DP.png --out /tmp/route.png
    wrote /tmp/route.png (592 x 416)
"""

import argparse
import sys
from typing import List, Optional

from pokenav.geometry import Tile
from pokenav.maps import render, schema
from pokenav.maps.render import Overlay, legs_through
from pokenav.maps.schema import MapImage
from pokenav.png import Image


def parse_tile(text: str) -> Tile:
    """A tile from "x,y"."""
    x, y = text.split(",")
    return Tile(int(x), int(y))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m pokenav.cli.render",
                                     description="Draw a route and regions over a map.")
    parser.add_argument("map", help="a map file (.json)")
    parser.add_argument("--path", nargs="*", default=[], help="waypoints x,y; each pair is a straight leg")
    parser.add_argument("--region", nargs="*", action="append", default=[], help="tiles x,y of one region")
    parser.add_argument("--image", help="the map's picture (PNG); lined up by the map file's image entry")
    parser.add_argument("--out", help="write a PNG here instead of printing text")
    args = parser.parse_args(argv)

    map_file = schema.load(args.map)
    overlay = Overlay(legs_through([parse_tile(t) for t in args.path]),
                      [{parse_tile(t) for t in region} for region in args.region])
    if not args.out:
        sys.stdout.write(render.ascii(map_file.grid, overlay))
        return 0
    if args.image:
        image = Image.read(args.image)
        calibration = map_file.image or MapImage(args.image)
    else:
        image = render.plain_image(map_file.grid)
        calibration = MapImage("", 0, 0, render.DEFAULT_TILE_PX)
    render.draw(image, calibration, overlay).write(args.out)
    print("wrote %s (%d x %d)" % (args.out, image.width, image.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
