"""Reads a tile grid and its named tiles from a navigation data file: a C++
data file (below), or a grid text file (games/<game>/maps/*.txt: one row per
line, `//` comments, `// Map: <name>` and `//   NAME x y` named tiles).

The data files (e.g. PokemonBDSP/Programs/AutoStory/Data/*_SandgemTown.cpp)
hold one grid as raw-string rows, `R"(...)"`, one per tile row, and named
tiles as `const TilePos NAME{x, y};`. Their header comment says which map
image the grid was read from and where its tile (0, 0) starts on it:
"Read from Bulbapedia's DP map of Sandgem Town (Sandgem_Town_DP.png,
560 x 368 px). The tile grid starts 8 px in from the left edge".
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

ROW = re.compile(r'R"\((.*)\)"')
TILE = re.compile(r'const\s+(?:Pokemon::)?TilePos\s+(\w+)\s*\{\s*(-?\d+)\s*,\s*(-?\d+)\s*\}')
#  The comment may wrap between the name and the size: "(Name.png,\n//  560 x 368 px)".
IMAGE = re.compile(r'\((\w[\w.-]*\.png),[\s/]*(\d+)\s*x\s*(\d+)\s*px\)')
LEFT = re.compile(r'starts\s+(\d+)\s*px\s+in\s+from\s+the\s+left', re.I)
NAMESPACE = re.compile(r'namespace\s+(\w+)\s*\{')
GENERIC_NAMESPACES = {'PokemonAutomation', 'NintendoSwitch', 'Pokemon', 'PokemonBDSP', 'PokemonFRLG', 'PokemonSV'}


@dataclass
class GridSource:
    name: str
    rows: list
    tiles: dict = field(default_factory=dict)
    image: str = ''
    image_size: tuple = (0, 0)
    origin: tuple = (0, 0)
    tile_px: int = 16

    @property
    def width(self):
        return max((len(r) for r in self.rows), default=0)


def map_label(namespace):
    """SandgemTown -> Sandgem Town, Route202 -> Route 202."""
    spaced = re.sub(r'(?<=[a-z])(?=[A-Z0-9])', ' ', namespace)
    return re.sub(r'(?<=[A-Za-z])(?=\d)', ' ', spaced)


def parse(text, name=''):
    rows = ROW.findall(text)
    tiles = {m.group(1): (int(m.group(2)), int(m.group(3))) for m in TILE.finditer(text)}
    namespaces = [n for n in NAMESPACE.findall(text) if n not in GENERIC_NAMESPACES]
    label = map_label(namespaces[-1]) if namespaces else name
    image = IMAGE.search(text)
    left = LEFT.search(text)
    return GridSource(
        name=label,
        rows=rows,
        tiles=tiles,
        image=image.group(1) if image else '',
        image_size=(int(image.group(2)), int(image.group(3))) if image else (0, 0),
        origin=(int(left.group(1)) if left else 0, 0),
    )


TEXT_MAP = re.compile(r'^//\s*Map:\s*(.+?)\s*$')
TEXT_TILE = re.compile(r'^//\s+([A-Z][A-Z0-9_]*)\s+(-?\d+)\s+(-?\d+)\s*$')


def parse_text(text, name=''):
    """A grid text file, the format cpp TileGrid::parse() reads."""
    rows, tiles, label = [], {}, name
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('//'):
            m = TEXT_MAP.match(stripped)
            if m:
                label = m.group(1)
            m = TEXT_TILE.match(stripped)
            if m:
                tiles[m.group(1)] = (int(m.group(2)), int(m.group(3)))
            continue
        rows.append(stripped.split()[0])
    image = IMAGE.search(text)
    left = LEFT.search(text)
    return GridSource(
        name=label,
        rows=rows,
        tiles=tiles,
        image=image.group(1) if image else '',
        image_size=(int(image.group(2)), int(image.group(3))) if image else (0, 0),
        origin=(int(left.group(1)) if left else 0, 0),
    )


def load(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    if path.suffix == '.txt':
        return parse_text(text, path.stem)
    return parse(text, path.stem)
