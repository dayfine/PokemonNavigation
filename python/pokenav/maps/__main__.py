"""maps: fetch a map image, and draw a navigation grid and logged routes over it.

    python3 -m pokenav.maps fetch Sandgem_Town_DP.png
    python3 -m pokenav.maps overlay <Data/..._SandgemTown.cpp> [--log SerialPrograms.log [--walk LABEL]] -o out.svg
"""
import argparse
import sys
from pathlib import Path

from . import fetch, grid_source, route_log, svg

CACHE = Path.home() / '.cache' / 'maps'


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m pokenav.maps")
    sub = parser.add_subparsers(dest='command', required=True)
    get = sub.add_parser('fetch', help='download a Bulbapedia map image into the cache')
    get.add_argument('name', help='file name on Bulbapedia, e.g. Sandgem_Town_DP.png')
    get.add_argument('--cache', type=Path, default=CACHE)
    draw = sub.add_parser('overlay', help='draw a data file\'s grid, and logged routes, over its map image')
    draw.add_argument('source', type=Path, help='the C++ data file with the grid')
    draw.add_argument('--image', type=Path, help='the map image; default: the one the file names, fetched')
    draw.add_argument('--log', type=Path, help='a SerialPrograms log to take planned walks from')
    draw.add_argument('--walk', action='append', help='only walks with this label (repeatable)')
    draw.add_argument('--last', type=int, default=0, help='only the last N walks')
    draw.add_argument('--cache', type=Path, default=CACHE)
    draw.add_argument('-o', '--out', type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == 'fetch':
        print(fetch.fetch(args.name, args.cache))
        return 0

    source = grid_source.load(args.source)
    image = args.image
    if image is None and source.image:
        image = fetch.fetch(source.image, args.cache)
    walks = []
    if args.log:
        lines = args.log.read_text(encoding='utf-8', errors='replace').splitlines()
        walks = route_log.parse(lines)
        if args.walk:
            walks = [w for w in walks if w.label in args.walk]
        walks = [w for w in walks if any(p[0] == source.name for p in w.start + [e for l in w.legs for e in l.ends])]
        if args.last:
            walks = walks[-args.last:]
    title = f'{source.name}: {len(source.rows)} rows x {source.width}, {len(walks)} walk(s)'
    args.out.write_text(svg.render(source, image.read_bytes() if image else None, walks, title), encoding='utf-8')
    print(args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
