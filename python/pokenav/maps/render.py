"""Draw routes and belief sets over a map: on the map's picture (PNG), or as
text for tests and terminals.

An `Overlay` is what to draw: legs (each the list of tiles it walks, in
order) and regions (sets of tiles the player may be on, such as a belief
set). On a picture, regions are tinted squares, legs are bars between tile
centers in alternating colors, the start is an outlined square and the end a
filled one. The picture is lined up with the grid by the map file's `image`
(origin and tile size); with no picture, cells are drawn as flat colors.

Command line (from the repository root):

    PYTHONPATH=python python3 -m pokenav.maps.render games/bdsp/maps/route_202.json \\
        --path 19,22 30,22 30,19 --region 29,19 30,19
    ...
    ###,,,,,,......,,,,,,..o*X.....#####   // row 19: the region, the path, the end
    ...

    PYTHONPATH=python python3 -m pokenav.maps.render games/bdsp/maps/route_202.json \\
        --path 19,22 30,22 30,19 --image ~/maps/Route_202_DP.png --out /tmp/route.png
    wrote /tmp/route.png (592 x 416)
"""

import argparse
import sys
from typing import Collection, Dict, List, NamedTuple, Optional, Sequence

from pokenav.geometry import Tile
from pokenav.maps import schema
from pokenav.maps.model import Behavior, Cell, MapGrid
from pokenav.maps.schema import MapImage
from pokenav.maps.textgrid import STANDARD, Legend, show
from pokenav.png import Color, Image


class Overlay(NamedTuple):
    """What to draw over a map: legs as tile lists, and regions as tile sets."""

    legs: Sequence[Sequence[Tile]] = ()
    regions: Sequence[Collection[Tile]] = ()


#   Characters for the text form.
PATH_CHAR = "*"
START_CHAR = "@"
END_CHAR = "X"
REGION_CHAR = "o"

#   Colors for pictures (RGBA). Legs alternate so a turn shows where one ends.
LEG_COLORS: List[Color] = [(230, 40, 40, 255), (250, 170, 0, 255)]
REGION_COLOR: Color = (40, 110, 255, 110)
START_COLOR: Color = (255, 255, 255, 255)
END_COLOR: Color = (230, 40, 40, 255)
#   Bar width and marker sizes, as fractions of a tile.
BAR_FRACTION = 0.25
MARKER_FRACTION = 0.5
#   A start marker's outline width in pixels.
OUTLINE_PX = 2

#   Flat cell colors for maps without a picture.
CELL_COLORS: Dict[Behavior, Color] = {
    Behavior.TALL_GRASS: (90, 170, 90, 255),
    Behavior.WATER: (70, 120, 220, 255),
    Behavior.DOOR: (150, 90, 40, 255),
    Behavior.WARP: (150, 90, 40, 255),
    Behavior.SIGN: (200, 160, 60, 255),
    Behavior.UNKNOWN: (0, 0, 0, 255),
}
OPEN_COLOR: Color = (230, 225, 200, 255)
WALL_COLOR: Color = (60, 60, 60, 255)
LEDGE_COLOR: Color = (130, 100, 60, 255)
#   The pixels per tile for a map without a picture.
DEFAULT_TILE_PX = 16


#   ---- text ----

def ascii(grid: MapGrid, overlay: Overlay, legend: Legend = STANDARD) -> str:
    """The grid as text with the overlay drawn on it: region tiles `o`, path
    tiles `*`, the start `@` and the end `X`."""
    return show(grid, legend, _marks(overlay))


def _marks(overlay: Overlay) -> Dict[Tile, str]:
    marks: Dict[Tile, str] = {}
    for region in overlay.regions:
        marks.update({tile: REGION_CHAR for tile in region})
    path = [tile for leg in overlay.legs for tile in leg]
    marks.update({tile: PATH_CHAR for tile in path})
    if path:
        marks[path[0]] = START_CHAR
        marks[path[-1]] = END_CHAR
    return marks


#   ---- pictures ----

def draw(image: Image, calibration: MapImage, overlay: Overlay) -> Image:
    """Draws `overlay` on `image` (in place), lined up by `calibration`."""
    for region in overlay.regions:
        for tile in region:
            _fill_tile(image, calibration, tile, 1.0, REGION_COLOR)
    for i, leg in enumerate(overlay.legs):
        _draw_leg(image, calibration, leg, LEG_COLORS[i % len(LEG_COLORS)])
    path = [tile for leg in overlay.legs for tile in leg]
    if path:
        _outline_tile(image, calibration, path[0], START_COLOR)
        _fill_tile(image, calibration, path[-1], MARKER_FRACTION, END_COLOR)
    return image


def plain_image(grid: MapGrid, tile_px: int = DEFAULT_TILE_PX) -> Image:
    """A picture of the grid in flat colors, for maps with no image."""
    image = Image(grid.width * tile_px, grid.height * tile_px)
    calibration = MapImage("", 0, 0, tile_px)
    for tile in grid.tiles():
        _fill_tile(image, calibration, tile, 1.0, cell_color(grid.at(tile)))
    return image


def cell_color(cell: Cell) -> Color:
    if cell.behavior in CELL_COLORS:
        return CELL_COLORS[cell.behavior]
    if cell.behavior.value.startswith("ledge"):
        return LEDGE_COLOR
    return WALL_COLOR if cell.blocked else OPEN_COLOR


def _center(calibration: MapImage, tile: Tile):
    half = calibration.tile_px // 2
    return (calibration.origin_x + tile.x * calibration.tile_px + half,
            calibration.origin_y + tile.y * calibration.tile_px + half)


def _fill_tile(image: Image, calibration: MapImage, tile: Tile, fraction: float, color: Color) -> None:
    """Fills a square of `fraction` of a tile, centered on `tile`."""
    cx, cy = _center(calibration, tile)
    half = max(1, round(calibration.tile_px * fraction / 2))
    image.fill_rect(cx - half, cy - half, cx + half, cy + half, color)


def _outline_tile(image: Image, calibration: MapImage, tile: Tile, color: Color) -> None:
    cx, cy = _center(calibration, tile)
    half = round(calibration.tile_px * MARKER_FRACTION / 2)
    x0, y0, x1, y1 = cx - half, cy - half, cx + half, cy + half
    for rect in ((x0, y0, x1, y0 + OUTLINE_PX), (x0, y1 - OUTLINE_PX, x1, y1),
                 (x0, y0, x0 + OUTLINE_PX, y1), (x1 - OUTLINE_PX, y0, x1, y1)):
        image.fill_rect(*rect, color)


def _draw_leg(image: Image, calibration: MapImage, leg: Sequence[Tile], color: Color) -> None:
    """A bar through the centers of consecutive tiles of `leg`."""
    half = max(1, round(calibration.tile_px * BAR_FRACTION / 2))
    for a, b in zip(leg, leg[1:]):
        (ax, ay), (bx, by) = _center(calibration, a), _center(calibration, b)
        image.fill_rect(min(ax, bx) - half, min(ay, by) - half, max(ax, bx) + half, max(ay, by) + half, color)


#   ---- command line ----

def legs_through(waypoints: Sequence[Tile]) -> List[List[Tile]]:
    """Straight legs between consecutive waypoints, each listing every tile
    from its start to its end. Raises ValueError for waypoints not in line."""
    legs = []
    for a, b in zip(waypoints, waypoints[1:]):
        direction = a.direction_to(b)
        if direction is None:
            raise ValueError("waypoints %s and %s are not in a straight line" % (a, b))
        legs.append([a.step(direction, i) for i in range(a.manhattan(b) + 1)])
    return legs


def _tile(text: str) -> Tile:
    x, y = text.split(",")
    return Tile(int(x), int(y))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m pokenav.maps.render",
                                     description="Draw a route and regions over a map.")
    parser.add_argument("map", help="a map file (.json)")
    parser.add_argument("--path", nargs="*", default=[], help="waypoints x,y; each pair is a straight leg")
    parser.add_argument("--region", nargs="*", action="append", default=[], help="tiles x,y of one region")
    parser.add_argument("--image", help="the map's picture (PNG); lined up by the map file's image entry")
    parser.add_argument("--out", help="write a PNG here instead of printing text")
    args = parser.parse_args(argv)

    map_file = schema.load(args.map)
    overlay = Overlay(legs_through([_tile(t) for t in args.path]),
                      [{_tile(t) for t in region} for region in args.region])
    if not args.out:
        sys.stdout.write(ascii(map_file.grid, overlay))
        return 0
    if args.image:
        image = Image.read(args.image)
        calibration = map_file.image or MapImage(args.image)
    else:
        image = plain_image(map_file.grid)
        calibration = MapImage("", 0, 0, DEFAULT_TILE_PX)
    draw(image, calibration, overlay).write(args.out)
    print("wrote %s (%d x %d)" % (args.out, image.width, image.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
