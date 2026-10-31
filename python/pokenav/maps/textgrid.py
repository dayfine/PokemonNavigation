"""Maps as text: the character legend, and a plain-text grid format.

The legend is one two-way table between characters and cell kinds (a cell's
`blocked` and `behavior`; elevation is its own layer). It is used to parse,
serialize and show grids; the map file (`maps.schema`) stays the source of
truth and stores its own legend.

The standard legend:

    #  wall               .  open ground        "  tall grass
    v ^ < >  ledges, crossed south / north / west / east
    D  door (walk into)   W  warp (step onto)   S  sign
    ~  water              =  counter            i  ice
    2 8 4 6  forced move south / north / west / east (as on a keypad)
    ?  unknown: off the map, or not checked yet
    N  an NPC standing on open ground (an object, not a cell)

The text format is the legend's rows, plus comments:

    // Map: Tiny Town           the map's name
    //   DOORSTEP 1 1           a named point: an upper-case name, x, y
    #D#   // 0                  a row; anything after "//" is ignored
    #N#   // 1
    // Elevation:               optional: as many rows of hex digits follow
    // 33 3                     (spaces are ignored)

Other comment lines are free text and are not kept.

The command line for showing and converting grids is `pokenav.cli.textgrid`.
"""

import re
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from pokenav.geometry import Direction, Tile
from pokenav.maps.model import OPEN, Behavior, Cell, GridMap2D
from pokenav.maps.schema import MapFile, NamedPoint, Npc


class Legend:
    """A two-way table between characters and cell kinds, plus the characters
    that mark an NPC on a tile (with the way the NPC faces, if the character
    says it).

    Each character stands for exactly one kind and each kind has exactly one
    character, so a grid written with a legend reads back the same.
    """

    def __init__(self, cells: Sequence[Tuple[str, Cell]], npcs: Sequence[Tuple[str, Optional[Direction]]] = ()):
        self._cell_by_char: Dict[str, Cell] = {}
        self._char_by_cell: Dict[Cell, str] = {}
        for char, cell in cells:
            self._add(char, cell._replace(elevation=0))
        self.npc_facing: Dict[str, Optional[Direction]] = dict(npcs)
        clash = set(self.npc_facing) & set(self._cell_by_char)
        if clash:
            raise ValueError("characters used for both cells and NPCs: %s" % sorted(clash))

    def _add(self, char: str, cell: Cell) -> None:
        if len(char) != 1:
            raise ValueError("legend key %r is not one character" % char)
        if char in self._cell_by_char or cell in self._char_by_cell:
            raise ValueError("legend entry %r -> %s is not one-to-one" % (char, cell))
        self._cell_by_char[char] = cell
        self._char_by_cell[cell] = char

    def cell(self, char: str) -> Cell:
        """The cell kind of `char` (elevation 0); KeyError if not a cell."""
        return self._cell_by_char[char]

    def char(self, cell: Cell) -> str:
        """The character of `cell`'s kind; KeyError if the legend has none."""
        return self._char_by_cell[cell._replace(elevation=0)]

    def show_char(self, cell: Cell) -> str:
        """The character to show `cell` with: its own if the legend has one,
        else that of the same behavior with the other collision, else a
        plain wall or open ground, else "?"."""
        kind = cell._replace(elevation=0)
        candidates = [kind, Cell(blocked=kind.blocked)]
        if kind.behavior is not Behavior.NONE:
            candidates.insert(1, kind._replace(blocked=not kind.blocked))
        for candidate in candidates:
            if candidate in self._char_by_cell:
                return self._char_by_cell[candidate]
        return "?"

    def npc_char(self, facing: Optional[Direction]) -> str:
        """The character marking an NPC that faces `facing`, or the plain NPC
        character if there is none for that facing."""
        for char, char_facing in self.npc_facing.items():
            if char_facing is facing:
                return char
        return next(iter(self.npc_facing))

    def cells(self) -> Dict[str, Cell]:
        """The cell part of the table, character to kind, in table order."""
        return dict(self._cell_by_char)


STANDARD = Legend(
    cells=[
        ("#", Cell(blocked=True)),
        (".", OPEN),
        ('"', Cell(behavior=Behavior.TALL_GRASS)),
        ("v", Cell(blocked=True, behavior=Behavior.LEDGE_SOUTH)),
        ("^", Cell(blocked=True, behavior=Behavior.LEDGE_NORTH)),
        ("<", Cell(blocked=True, behavior=Behavior.LEDGE_WEST)),
        (">", Cell(blocked=True, behavior=Behavior.LEDGE_EAST)),
        ("D", Cell(blocked=True, behavior=Behavior.DOOR)),
        ("W", Cell(behavior=Behavior.WARP)),
        ("S", Cell(blocked=True, behavior=Behavior.SIGN)),
        ("~", Cell(blocked=True, behavior=Behavior.WATER)),
        ("=", Cell(blocked=True, behavior=Behavior.COUNTER)),
        ("i", Cell(behavior=Behavior.ICE)),
        ("2", Cell(behavior=Behavior.FORCED_SOUTH)),
        ("8", Cell(behavior=Behavior.FORCED_NORTH)),
        ("4", Cell(behavior=Behavior.FORCED_WEST)),
        ("6", Cell(behavior=Behavior.FORCED_EAST)),
        ("?", Cell(blocked=True, behavior=Behavior.UNKNOWN)),
    ],
    npcs=[("N", None)],
)

_MAP_NAME = re.compile(r"^//\s*Map:\s*(.+?)\s*$")
_POINT = re.compile(r"^//\s+([A-Z][A-Z0-9_]*)\s+(-?\d+)\s+(-?\d+)\s*$")
_ELEVATION = re.compile(r"^//\s*Elevation:\s*$")


#   ---- parsing ----

def parse(text: str, legend: Legend = STANDARD, name: str = "") -> MapFile:
    """A map file from the text format. `name` is used if the text has no
    "// Map:" line. Raises ValueError for an unknown character or a row of
    the wrong width."""
    lines = text.splitlines()
    name = _find_name(lines) or name
    rows, elevation = _split_rows(lines)
    npcs = _npcs(rows, legend)
    cells = [[_cell(legend, char, x, y) for x, char in enumerate(row)] for y, row in enumerate(rows)]
    if elevation:
        cells = _with_elevation(cells, elevation)
    points = [NamedPoint(m.group(1), Tile(int(m.group(2)), int(m.group(3))))
              for m in map(_POINT.match, lines) if m]
    return MapFile(grid=GridMap2D(name, cells), points=points, npcs=npcs)


def _find_name(lines: Iterable[str]) -> str:
    for line in lines:
        match = _MAP_NAME.match(line.strip())
        if match:
            return match.group(1)
    return ""


def _split_rows(lines: List[str]) -> Tuple[List[str], List[str]]:
    """The grid rows, and the elevation rows after "// Elevation:"."""
    rows: List[str] = []
    elevation: List[str] = []
    in_elevation = False
    for line in (line.strip() for line in lines):
        if _ELEVATION.match(line):
            in_elevation = True
        elif in_elevation and line.startswith("//"):
            elevation.append(line[2:].replace(" ", ""))
        elif line and not line.startswith("//"):
            rows.append(line.split("//")[0].strip())
    return rows, [row for row in elevation if row]


def _cell(legend: Legend, char: str, x: int, y: int) -> Cell:
    if char in legend.npc_facing:
        return OPEN
    try:
        return legend.cell(char)
    except KeyError:
        raise ValueError("character %r at (%d, %d) is not in the legend" % (char, x, y)) from None


def _npcs(rows: List[str], legend: Legend) -> List[Npc]:
    npcs = []
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char in legend.npc_facing:
                npcs.append(Npc("npc_%d_%d" % (x, y), Tile(x, y), legend.npc_facing[char]))
    return npcs


def _with_elevation(cells: List[List[Cell]], elevation: List[str]) -> List[List[Cell]]:
    if len(elevation) != len(cells) or any(len(e) != len(r) for e, r in zip(elevation, cells)):
        raise ValueError("the elevation layer is not the size of the grid")
    return [[cell._replace(elevation=int(level, 16)) for cell, level in zip(row, levels)]
            for row, levels in zip(cells, elevation)]


#   ---- serializing and showing ----

def serialize(map_file: MapFile, legend: Legend = STANDARD) -> str:
    """The text format of `map_file`: name, named points, rows with NPCs
    marked, and the elevation layer if any tile is above 0. Raises KeyError
    for a cell the legend has no character for."""
    grid = map_file.grid
    lines = ["// Map: %s" % grid.name]
    lines += ["//   %s %d %d" % (p.name, p.tile.x, p.tile.y) for p in map_file.points]
    rows = _char_rows(grid, legend.char)
    _mark_npcs(rows, map_file.npcs, legend)
    lines += ["%s  // %d" % ("".join(row), y) for y, row in enumerate(rows)]
    lines += _elevation_lines(grid)
    return "\n".join(lines) + "\n"


def show(grid: GridMap2D, legend: Legend = STANDARD, marks: Optional[Mapping[Tile, str]] = None) -> str:
    """The grid as rows of characters, for printing and tests. Cells the
    legend has no character for are shown by their nearest kind, and
    `marks` (tile to character) are drawn over the cells."""
    rows = _char_rows(grid, legend.show_char)
    for tile, char in (marks or {}).items():
        if grid.contains(tile):
            rows[tile.y][tile.x] = char
    return "\n".join("".join(row) for row in rows) + "\n"


def _char_rows(grid: GridMap2D, char_of) -> List[List[str]]:
    return [[char_of(cell) for cell in row] for row in grid.rows()]


def _mark_npcs(rows: List[List[str]], npcs: Iterable[Npc], legend: Legend) -> None:
    for npc in npcs:
        rows[npc.tile.y][npc.tile.x] = legend.npc_char(npc.facing)


def _elevation_lines(grid: GridMap2D) -> List[str]:
    levels = ["".join("%X" % cell.elevation for cell in row) for row in grid.rows()]
    if not any(level.strip("0") for level in levels):
        return []
    return ["// Elevation:"] + ["// " + level for level in levels]
