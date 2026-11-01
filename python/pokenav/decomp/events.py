"""Map events of the DS Sinnoh games: the objects on a map (people, signs,
item balls, obstacles), its warps and its background sign events.

Platinum keeps them as JSON (res/field/events/events_<map>.json) with
named constants; Diamond as binary (files/fielddata/eventdata/
zone_event_release/narc_NNNN.bin): a u32 count and the records of each kind
in turn, background events (20 bytes: script, type, x, z as u16/u16/u32/u32,
then y and the facing), object events (32 bytes, pokediamond
include/map_object.h struct ObjectEvent), warps (12 bytes: x, z, map, warp,
y) and coordinate events (16 bytes, not read). Diamond numbers its sprites
and movement types; the names come from the caller (`repos`).

Background events are signs read facing a tile (type 0), wall signs (type
1) and hidden items (type 2; pokeplatinum generated/bg_event_types.txt);
only the signs are kept. Signposts you can walk around are object events
with signpost graphics.

Both read into the same records, so a map generates the same from either
game where the games agree:

    events = events_from_json(json.load(open("events_route_201.json")))
    events.objects[1]      # ObjectEvent(name='cashier_m', graphic='CASHIER_M', movement='LOOK_SOUTH_AND_EAST', ...)
"""

import enum
import struct
from typing import List, Mapping, NamedTuple, Optional

from pokenav.grid.geometry import Direction

#   Movement types by number: the order of pokeplatinum
#   generated/movement_types.txt (the named ones, 0 to 54), which Diamond's
#   binary records index.
MOVEMENT_TYPES = (
    "NONE", "PLAYER", "LOOK_AROUND", "WANDER_AROUND", "WANDER_NORTH_AND_SOUTH",
    "WANDER_WEST_AND_EAST", "LOOK_NORTH_AND_WEST", "LOOK_NORTH_AND_EAST", "LOOK_SOUTH_AND_WEST",
    "LOOK_SOUTH_AND_EAST", "LOOK_NORTH_SOUTH_AND_WEST", "LOOK_NORTH_SOUTH_AND_EAST",
    "LOOK_NORTH_WEST_AND_EAST", "LOOK_SOUTH_WEST_AND_EAST", "LOOK_NORTH", "LOOK_SOUTH",
    "LOOK_WEST", "LOOK_EAST", "ROTATE_COUNTERCLOCKWISE", "ROTATE_CLOCKWISE",
    "WALK_BACK_AND_FORTH", "WALK_NORTH_EAST_WEST_SOUTH", "WALK_EAST_WEST_SOUTH_NORTH",
    "WALK_SOUTH_NORTH_EAST_WEST", "WALK_WEST_SOUTH_NORTH_EAST", "WALK_WEST_EAST_SOUTH_NORTH",
    "WALK_NORTH_WEST_EAST_SOUTH", "WALK_SOUTH_NORTH_WEST_EAST", "WALK_EAST_SOUTH_NORTH_WEST",
    "WALK_WEST_NORTH_SOUTH_EAST", "WALK_NORTH_SOUTH_EAST_WEST", "WALK_EAST_WEST_NORTH_SOUTH",
    "WALK_SOUTH_EAST_WEST_NORTH", "WALK_EAST_NORTH_SOUTH_WEST", "WALK_NORTH_SOUTH_WEST_EAST",
    "WALK_WEST_EAST_NORTH_SOUTH", "WALK_SOUTH_WEST_EAST_NORTH", "WALK_NORTH_WEST_SOUTH_EAST",
    "WALK_SOUTH_EAST_NORTH_WEST", "WALK_WEST_SOUTH_EAST_NORTH", "WALK_EAST_NORTH_WEST_SOUTH",
    "WALK_NORTH_EAST_SOUTH_WEST", "WALK_SOUTH_WEST_NORTH_EAST", "WALK_WEST_NORTH_EAST_SOUTH",
    "WALK_EAST_SOUTH_WEST_NORTH", "LOOK_NORTH_AND_SOUTH", "LOOK_WEST_AND_EAST", "BERRY_SOIL",
    "FOLLOW_PLAYER", "VS_SEEKER_SPIN", "FOLLOW_PARTNER_TRAINER", "DISGUISE_SNOW",
    "DISGUISE_SAND", "DISGUISE_ROCK", "DISGUISE_GRASS",
)

#   Initial facings (DIR_* in pokeplatinum include/constants/map_object.h).
DIRECTIONS = {0: Direction.NORTH, 1: Direction.SOUTH, 2: Direction.WEST, 3: Direction.EAST}

#   Background event types that are signs (BG_EVENT_TYPE_FACING and
#   BG_EVENT_TYPE_WALL_SIGN); type 2 is a hidden item.
SIGN_TYPES = (0, 1)

#   How far a trainer sees when the events do not say.
DEFAULT_SIGHT = 4

#   Prefixes the JSON constants carry.
_LOCALID = "LOCALID_"
_GRAPHIC = "OBJ_EVENT_GFX_"
_MOVEMENT = "MOVEMENT_TYPE_"
_NO_TRAINER = "TRAINER_TYPE_NONE"


class Kind(enum.Enum):
    """What an object is to a walker."""

    PERSON = "person"
    SIGN = "sign"           # a signpost: blocks its tile, read from below
    ITEM = "item"           # a Poke Ball on the ground: blocks until picked up
    ROCK = "rock"           # a Rock Smash rock
    BOULDER = "boulder"     # a Strength boulder
    TREE = "tree"           # a Cut tree


#   Graphics that are not people, under Platinum's names and Diamond's
#   (pokediamond include/constants/sprites.h; Diamond's signpost sprites
#   are unnamed there and get Platinum's names in `repos`).
GRAPHIC_KINDS = {
    "ARROW_SIGNPOST": Kind.SIGN, "SIGNBOARD": Kind.SIGN, "MAP_SIGNPOST": Kind.SIGN,
    "TRAINER_TIPS_SIGNPOST": Kind.SIGN, "GYM_SIGNPOST": Kind.SIGN, "MAILBOX": Kind.SIGN,
    "POKEBALL": Kind.ITEM, "MONSTARBALL": Kind.ITEM,
    "ROCK_SMASH": Kind.ROCK, "BREAKROCK": Kind.ROCK,
    "STRENGTH_BOULDER": Kind.BOULDER, "ROCK": Kind.BOULDER,
    "CUT_TREE": Kind.TREE, "TREE": Kind.TREE,
}


class ObjectEvent(NamedTuple):
    """One object on the map. `movement` is the type without its prefix
    (LOOK_SOUTH, WANDER_AROUND); `facing` the way a standing object looks;
    `sight` how far a trainer sees (0 for anyone else); `hidden` the flag
    that hides the object, or "" if none."""

    name: str
    graphic: str
    movement: str
    x: int
    z: int
    facing: Optional[Direction] = None
    range_x: int = 0
    range_z: int = 0
    sight: int = 0
    hidden: str = ""

    @property
    def kind(self) -> Kind:
        return GRAPHIC_KINDS.get(self.graphic, Kind.PERSON)

    @property
    def wanders(self) -> bool:
        """Whether the object moves about (WANDER_* and WALK_* movements
        with a range)."""
        moving = self.movement.startswith("WANDER") or self.movement.startswith("WALK")
        return moving and (self.range_x > 0 or self.range_z > 0)


class WarpEvent(NamedTuple):
    """A warp: the tile, the destination map's constant and warp index."""

    x: int
    z: int
    to_map: str
    to_warp: int


class SignEvent(NamedTuple):
    """A background sign event: a script read by facing the tile."""

    x: int
    z: int
    script: int


class Events(NamedTuple):
    objects: List[ObjectEvent]
    warps: List[WarpEvent]
    signs: List[SignEvent]


def facing_of(movement: str, initial_dir: Optional[int]) -> Optional[Direction]:
    """The way a standing object looks: the first direction of a LOOK_*
    movement, else its initial facing. None for one that moves about."""
    if movement.startswith("WANDER") or movement.startswith("WALK"):
        return None
    if movement.startswith("LOOK_"):
        for name, direction in (("NORTH", Direction.NORTH), ("SOUTH", Direction.SOUTH),
                                ("WEST", Direction.WEST), ("EAST", Direction.EAST)):
            if movement[len("LOOK_"):].startswith(name):
                return direction
    return DIRECTIONS.get(initial_dir) if initial_dir is not None else None


#   ---- Platinum ----

def events_from_json(data: Mapping) -> Events:
    """Platinum's events file."""
    return Events(
        objects=[_object_from_json(i, o) for i, o in enumerate(data.get("object_events") or [])],
        warps=[WarpEvent(w["x"], w["z"], w["dest_header_id"], int(w["dest_warp_id"]))
               for w in data.get("warp_events") or []],
        signs=[SignEvent(b["x"], b["z"], int(b["script"])) for b in data.get("bg_events") or []
               if b.get("type") in SIGN_TYPES],
    )


def _object_from_json(index: int, data: Mapping) -> ObjectEvent:
    movement = _strip(data.get("movement_type", ""), _MOVEMENT)
    sight = 0
    if data.get("trainer_type", _NO_TRAINER) != _NO_TRAINER:
        values = data.get("data") or []
        sight = int(values[0]) if values else DEFAULT_SIGHT
    hidden = str(data.get("hidden_flag", "0"))
    name = _strip(data.get("id", ""), _LOCALID) or "object_%d" % index
    return ObjectEvent(
        name=name.lower(),
        graphic=_strip(data.get("graphics_id", ""), _GRAPHIC),
        movement=movement,
        x=int(data["x"]),
        z=int(data["z"]),
        facing=facing_of(movement, data.get("initial_dir")),
        range_x=int(data.get("movement_range_x", 0)),
        range_z=int(data.get("movement_range_z", 0)),
        sight=sight,
        hidden="" if hidden == "0" else hidden,
    )


def _strip(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


#   ---- Diamond ----

_BG_RECORD = struct.Struct("<HHIIiI")
_OBJECT_RECORD = struct.Struct("<HHHHHHhHHHhhHHi")
_WARP_RECORD = struct.Struct("<HHHHi")
_COORD_RECORD_SIZE = 16


def events_from_binary(data: bytes, graphic_names: Mapping[int, str], map_names: Mapping[int, str]) -> Events:
    """Diamond's zone events. `graphic_names` names sprite ids and
    `map_names` map ids (both from the checkout's constants)."""
    offset = 0
    count, offset = _count(data, offset)
    signs = []
    for _ in range(count):
        script, kind, x, z, _, _ = _BG_RECORD.unpack_from(data, offset)
        offset += _BG_RECORD.size
        if kind in SIGN_TYPES:
            signs.append(SignEvent(x, z, script))
    count, offset = _count(data, offset)
    objects = []
    for index in range(count):
        objects.append(_object_from_record(index, _OBJECT_RECORD.unpack_from(data, offset), graphic_names))
        offset += _OBJECT_RECORD.size
    count, offset = _count(data, offset)
    warps = []
    for _ in range(count):
        x, z, map_id, warp_id, _ = _WARP_RECORD.unpack_from(data, offset)
        offset += _WARP_RECORD.size
        warps.append(WarpEvent(x, z, map_names.get(map_id, "MAP_%d" % map_id), warp_id))
    count, offset = _count(data, offset)
    offset += count * _COORD_RECORD_SIZE
    if offset != len(data):
        raise ValueError("zone events: %d bytes read of %d" % (offset, len(data)))
    return Events(objects, warps, signs)


def _count(data: bytes, offset: int):
    return struct.unpack_from("<I", data, offset)[0], offset + 4


def _object_from_record(index: int, fields, graphic_names: Mapping[int, str]) -> ObjectEvent:
    (_, sprite, movement_id, trainer, flag, _, initial_dir,
     sight, _, _, range_x, range_z, x, z, _) = fields
    graphic = graphic_names.get(sprite, "SPRITE_%d" % sprite)
    movement = MOVEMENT_TYPES[movement_id] if movement_id < len(MOVEMENT_TYPES) else "MOVEMENT_%d" % movement_id
    return ObjectEvent(
        name=graphic.lower(),
        graphic=graphic,
        movement=movement,
        x=x,
        z=z,
        facing=facing_of(movement, initial_dir),
        range_x=range_x,
        range_z=range_z,
        sight=(sight or DEFAULT_SIGHT) if trainer else 0,
        hidden="" if flag == 0 else "flag %d" % flag,
    )
