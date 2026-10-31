"""The JSON map file: one map's cells and what is on it, the source of truth
for a map.

A map file is meant to be read and edited by hand. Cells are written as rows
of characters with the legend that decodes them in the same file, so a map
reads like a picture; everything else is a named record:

    {
      "format": "pokenav-map/1",
      "name": "Tiny Town",
      "game": "example",
      "legend": {
        "#": {"blocked": true},
        ".": {},
        "D": {"blocked": true, "behavior": "door"}
      },
      "rows": [
        "#D#",
        "#.#"
      ],
      "elevation": ["333", "333"],
      "points": [{"name": "DOORSTEP", "tile": [1, 1], "proof": "the door is north"}],
      "npcs": [{"name": "guard", "tile": [1, 1], "facing": "south", "sight": 3}],
      "signs": [{"name": "town_sign", "tile": [0, 0], "facing": "north"}],
      "buildings": [{"name": "Mart", "kind": "mart", "door": [1, 0]}],
      "warps": [{"tile": [1, 0], "to_map": "Tiny Mart", "to_warp": 0}],
      "connections": [{"direction": "south", "map": "Route 9", "offset": -4}],
      "notes": [{"text": "door row measured by walking north", "source": "console"}]
    }

Only "format", "name", "legend" and "rows" are required. "elevation" is one
hex digit (0 to F) per tile and defaults to all 0. A legend entry gives a
cell's `blocked` (default false) and `behavior` (default "none"); its
elevation comes from the elevation rows. The legend is the file's own, so a
file can use any characters; `maps.textgrid` has the standard one.

The example above is docs/examples/tiny_town.json:

    town = load("docs/examples/tiny_town.json")
    town.grid.at(Tile(1, 0)).behavior   # Behavior.DOOR
    town.npcs[0].sight                  # 3
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from pokenav.geometry import Direction, Tile
from pokenav.maps.model import Behavior, Cell, MapGrid

#   The value of "format" this module reads and writes.
FORMAT = "pokenav-map/1"

#   Elevation rows use one hex digit per tile.
_HEX_DIGITS = "0123456789ABCDEF"


@dataclass
class NamedPoint:
    """A tile worth a name: a save spot, an anchor, an exit. `proof` says how
    a walk can tell it stands there (two walls, a sign read)."""

    name: str
    tile: Tile
    proof: str = ""
    note: str = ""


@dataclass
class Wander:
    """Where a wandering NPC may stand: the rectangle from `low` to `high`
    (inclusive), and how many steps a second it takes, if measured."""

    low: Tile
    high: Tile
    rate: Optional[float] = None


@dataclass
class Npc:
    """A person on the map. `sight` > 0 marks a trainer who sees that many
    tiles in front of them. `wander` is None for one who stands still."""

    name: str
    tile: Tile
    facing: Optional[Direction] = None
    sight: int = 0
    wander: Optional[Wander] = None
    note: str = ""


@dataclass
class Sign:
    """A sign on `tile`, read by standing next to it facing `facing`."""

    name: str
    tile: Tile
    facing: Direction = Direction.NORTH
    note: str = ""


@dataclass
class Building:
    """A building entered through `door`; `kind` is e.g. "pokecenter",
    "mart", "gym" or "house"."""

    name: str
    kind: str
    door: Tile
    note: str = ""


@dataclass
class Warp:
    """A warp tile: it leads to warp number `to_warp` of map `to_map`."""

    tile: Tile
    to_map: str
    to_warp: int


@dataclass
class Connection:
    """The map past one edge. `offset` is how far the other map is shifted
    along that edge, in tiles: its x (for north and south) or y (for east and
    west) equals this map's minus `offset`."""

    direction: Direction
    map: str
    offset: int = 0


@dataclass
class Note:
    """A fact about the map and where it came from (a console run, an image,
    the decompilation)."""

    text: str
    source: str = ""


@dataclass
class MapFile:
    """Everything a map file holds."""

    grid: MapGrid
    game: str = ""
    points: List[NamedPoint] = field(default_factory=list)
    npcs: List[Npc] = field(default_factory=list)
    signs: List[Sign] = field(default_factory=list)
    buildings: List[Building] = field(default_factory=list)
    warps: List[Warp] = field(default_factory=list)
    connections: List[Connection] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.grid.name

    def point(self, name: str) -> NamedPoint:
        """The named point called `name`; KeyError if there is none."""
        for point in self.points:
            if point.name == name:
                return point
        raise KeyError("map %r has no point %r" % (self.name, name))


#   A legend: each character and the cell kind (blocked, behavior) it stands
#   for. Elevation is not part of it.
Legend = Mapping[str, Cell]


def load(path: str) -> MapFile:
    """Reads a map file. Raises ValueError naming the file if it is invalid."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        return loads(text)
    except ValueError as e:
        raise ValueError("%s: %s" % (path, e)) from None


def loads(text: str) -> MapFile:
    """Parses a map file's text."""
    return from_json(json.loads(text))


def dump(path: str, map_file: MapFile, legend: Legend) -> None:
    """Writes a map file, encoding cells with `legend`."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(dumps(map_file, legend))


def dumps(map_file: MapFile, legend: Legend) -> str:
    """The map file's text, encoding cells with `legend`: one line per legend
    entry, row and record, so the rows read as a picture and a diff shows
    which record changed."""
    return format_json(to_json(map_file, legend))


def format_json(data: Dict[str, Any]) -> str:
    """JSON text for a parsed map file with each top-level list item or
    object entry on its own line."""
    lines = []
    for key, value in data.items():
        lines.append("  %s: %s" % (_compact(key), _block(value)))
    return "{\n" + ",\n".join(lines) + "\n}\n"


def _block(value: Any) -> str:
    if isinstance(value, list) and value:
        items = ",\n".join("    " + _compact(item) for item in value)
        return "[\n" + items + "\n  ]"
    if isinstance(value, dict) and value:
        items = ",\n".join("    %s: %s" % (_compact(k), _compact(v)) for k, v in value.items())
        return "{\n" + items + "\n  }"
    return _compact(value)


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def from_json(data: Dict[str, Any]) -> MapFile:
    """A MapFile from a parsed map file."""
    if data.get("format") != FORMAT:
        raise ValueError("format is %r, expected %r" % (data.get("format"), FORMAT))
    grid = _grid_from_json(data)
    return MapFile(
        grid=grid,
        game=data.get("game", ""),
        points=[_point_from_json(p) for p in data.get("points", [])],
        npcs=[_npc_from_json(n) for n in data.get("npcs", [])],
        signs=[_sign_from_json(s) for s in data.get("signs", [])],
        buildings=[_building_from_json(b) for b in data.get("buildings", [])],
        warps=[_warp_from_json(w) for w in data.get("warps", [])],
        connections=[_connection_from_json(c) for c in data.get("connections", [])],
        notes=[Note(n["text"], n.get("source", "")) for n in data.get("notes", [])],
    )


def to_json(map_file: MapFile, legend: Legend) -> Dict[str, Any]:
    """The parsed form of the map file for `map_file`. Lists that are empty
    and an all-zero elevation layer are left out."""
    data: Dict[str, Any] = {"format": FORMAT, "name": map_file.name}
    if map_file.game:
        data["game"] = map_file.game
    data.update(_grid_to_json(map_file.grid, legend))
    records = {
        "points": [_point_to_json(p) for p in map_file.points],
        "npcs": [_npc_to_json(n) for n in map_file.npcs],
        "signs": [_sign_to_json(s) for s in map_file.signs],
        "buildings": [_building_to_json(b) for b in map_file.buildings],
        "warps": [_warp_to_json(w) for w in map_file.warps],
        "connections": [_connection_to_json(c) for c in map_file.connections],
        "notes": [_drop_empty({"text": n.text, "source": n.source}) for n in map_file.notes],
    }
    data.update({key: value for key, value in records.items() if value})
    return data


#   ---- cells ----

def _grid_from_json(data: Dict[str, Any]) -> MapGrid:
    legend = {char: _legend_cell(char, spec) for char, spec in data["legend"].items()}
    rows: List[str] = data["rows"]
    elevation: List[str] = data.get("elevation") or ["0" * len(row) for row in rows]
    if len(elevation) != len(rows):
        raise ValueError("%d elevation rows for %d rows" % (len(elevation), len(rows)))
    cells = [_decode_row(y, row, levels, legend) for y, (row, levels) in enumerate(zip(rows, elevation))]
    return MapGrid(data["name"], cells)


def _legend_cell(char: str, spec: Dict[str, Any]) -> Cell:
    if len(char) != 1:
        raise ValueError("legend key %r is not one character" % char)
    return Cell(blocked=bool(spec.get("blocked", False)),
                behavior=Behavior(spec.get("behavior", Behavior.NONE.value)))


def _decode_row(y: int, row: str, levels: str, legend: Mapping[str, Cell]) -> List[Cell]:
    if len(levels) != len(row):
        raise ValueError("elevation row %d has %d digits for %d tiles" % (y, len(levels), len(row)))
    cells = []
    for x, (char, level) in enumerate(zip(row, levels)):
        if char not in legend:
            raise ValueError("character %r at (%d, %d) is not in the legend" % (char, x, y))
        if level.upper() not in _HEX_DIGITS:
            raise ValueError("elevation %r at (%d, %d) is not a hex digit" % (level, x, y))
        cells.append(legend[char]._replace(elevation=int(level, 16)))
    return cells


def _grid_to_json(grid: MapGrid, legend: Legend) -> Dict[str, Any]:
    chars = {cell: char for char, cell in legend.items()}
    rows = [_encode_row(y, row, chars) for y, row in enumerate(grid.rows())]
    used = sorted(set("".join(rows)), key=list(legend).index)
    data: Dict[str, Any] = {
        "legend": {char: _legend_spec(legend[char]) for char in used},
        "rows": rows,
    }
    levels = ["".join(_HEX_DIGITS[cell.elevation] for cell in row) for row in grid.rows()]
    if any(level.strip("0") for level in levels):
        data["elevation"] = levels
    return data


def _encode_row(y: int, row: List[Cell], chars: Mapping[Cell, str]) -> str:
    kinds = [cell._replace(elevation=0) for cell in row]
    missing = [(x, kind) for x, kind in enumerate(kinds) if kind not in chars]
    if missing:
        x, kind = missing[0]
        raise ValueError("cell %s at (%d, %d) has no legend character" % (kind, x, y))
    return "".join(chars[kind] for kind in kinds)


def _legend_spec(cell: Cell) -> Dict[str, Any]:
    spec: Dict[str, Any] = {}
    if cell.blocked:
        spec["blocked"] = True
    if cell.behavior is not Behavior.NONE:
        spec["behavior"] = cell.behavior.value
    return spec


#   ---- records ----

def _tile(value: List[int]) -> Tile:
    x, y = value
    return Tile(int(x), int(y))


def _direction(value: Optional[str]) -> Optional[Direction]:
    return None if value is None else Direction.parse(value)


def _drop_empty(data: Dict[str, Any]) -> Dict[str, Any]:
    """`data` without keys whose value is None, "" or 0, to keep files short."""
    return {key: value for key, value in data.items() if value not in (None, "", 0)}


def _point_from_json(data: Dict[str, Any]) -> NamedPoint:
    return NamedPoint(data["name"], _tile(data["tile"]), data.get("proof", ""), data.get("note", ""))


def _point_to_json(point: NamedPoint) -> Dict[str, Any]:
    return _drop_empty({"name": point.name, "tile": list(point.tile),
                        "proof": point.proof, "note": point.note})


def _npc_from_json(data: Dict[str, Any]) -> Npc:
    wander = data.get("wander")
    return Npc(
        name=data["name"],
        tile=_tile(data["tile"]),
        facing=_direction(data.get("facing")),
        sight=int(data.get("sight", 0)),
        wander=None if wander is None else Wander(_tile(wander["low"]), _tile(wander["high"]), wander.get("rate")),
        note=data.get("note", ""),
    )


def _npc_to_json(npc: Npc) -> Dict[str, Any]:
    wander = None
    if npc.wander is not None:
        wander = _drop_empty({"low": list(npc.wander.low), "high": list(npc.wander.high), "rate": npc.wander.rate})
    return _drop_empty({
        "name": npc.name,
        "tile": list(npc.tile),
        "facing": npc.facing.name.lower() if npc.facing else None,
        "sight": npc.sight,
        "wander": wander,
        "note": npc.note,
    })


def _sign_from_json(data: Dict[str, Any]) -> Sign:
    return Sign(data["name"], _tile(data["tile"]),
                _direction(data.get("facing", "north")), data.get("note", ""))


def _sign_to_json(sign: Sign) -> Dict[str, Any]:
    return _drop_empty({"name": sign.name, "tile": list(sign.tile),
                        "facing": sign.facing.name.lower(), "note": sign.note})


def _building_from_json(data: Dict[str, Any]) -> Building:
    return Building(data["name"], data["kind"], _tile(data["door"]), data.get("note", ""))


def _building_to_json(building: Building) -> Dict[str, Any]:
    return _drop_empty({"name": building.name, "kind": building.kind,
                        "door": list(building.door), "note": building.note})


def _warp_from_json(data: Dict[str, Any]) -> Warp:
    return Warp(_tile(data["tile"]), data["to_map"], int(data["to_warp"]))


def _warp_to_json(warp: Warp) -> Dict[str, Any]:
    return {"tile": list(warp.tile), "to_map": warp.to_map, "to_warp": warp.to_warp}


def _connection_from_json(data: Dict[str, Any]) -> Connection:
    return Connection(Direction.parse(data["direction"]), data["map"], int(data.get("offset", 0)))


def _connection_to_json(connection: Connection) -> Dict[str, Any]:
    return {"direction": connection.direction.name.lower(), "map": connection.map,
            "offset": connection.offset}
