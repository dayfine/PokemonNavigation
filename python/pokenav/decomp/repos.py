"""Where each Sinnoh decompilation keeps its land data, matrices and events,
and how its constants are named.

pret data is not committed here; a `Repo` reads a local checkout (or a copy
with the same relative paths). `Platinum` reads pret/pokeplatinum, whose
matrices and events are JSON with named constants; `Diamond` reads
pret/pokediamond, whose files are binary with numbered sprites and maps, so
it also reads include/constants/maps.h and include/constants/sprites.h for
the names. The commit a checkout is at comes from .git/HEAD, or is given.

    repo = open_repo("pokediamond", "/path/to/pokediamond")
    repo.matrix(0).headers[26][3]          # 'MAP_ROUTE_201'
    repo.land(5)[10 * 32 + 44]             # 2: tall grass
    repo.events("327").objects[1].graphic  # 'SHOPM1'
    repo.map_name("MAP_SANDGEM")           # 'Sandgem Town'
"""

import json
import os
import re
from typing import Dict, Mapping, Optional, Tuple

from pokenav.decomp import events, landdata
from pokenav.decomp.events import Events
from pokenav.decomp.landdata import Matrix

#   GitHub owner of both decompilations.
OWNER = "pret"

#   Display names for map constants whose words are not the place's name:
#   Diamond's town constants are the bare town name, misspelled for one.
MAP_NAMES = {
    "JUBLIFE": "Jubilife City",
    "JUBILIFE": "Jubilife City",
    "SANDGEM": "Sandgem Town",
    "TWINLEAF": "Twinleaf Town",
    "FLOAROMA": "Floaroma Town",
    "OREBURGH": "Oreburgh City",
    "ETERNA": "Eterna City",
}

#   Diamond sprites that pokediamond's sprites.h leaves unnamed, named as
#   pokeplatinum generated/object_events_gfx.txt names the same numbers
#   (matched by tile against Platinum's events for Route 201, Sandgem Town,
#   Jubilife City and Route 204).
DIAMOND_SPRITE_NAMES = {
    91: "MAP_SIGNPOST",
    92: "MAILBOX",
    93: "SIGNBOARD",
    94: "ARROW_SIGNPOST",
    95: "GYM_SIGNPOST",
    96: "TRAINER_TIPS_SIGNPOST",
    101: "VAR_0",
}

#   Words of map constants that title-casing gets wrong.
WORDS = {"JUBLIFE": "Jubilife", "TV": "TV", "GTS": "GTS", "1F": "1F", "2F": "2F", "3F": "3F", "4F": "4F",
         "B1F": "B1F", "B2F": "B2F", "B3F": "B3F"}

_DEFINE = re.compile(r"^#define\s+(\w+)\s+(\d+)")


def display_name(constant: str) -> str:
    """The place a map constant names: MAP_HEADER_ROUTE_201 and MAP_ROUTE_201
    are "Route 201", MAP_SANDGEM_TOWN and MAP_SANDGEM "Sandgem Town"."""
    for prefix in ("MAP_HEADER_", "MAP_"):
        if constant.startswith(prefix):
            constant = constant[len(prefix):]
            break
    if constant in MAP_NAMES:
        return MAP_NAMES[constant]
    return " ".join(WORDS.get(word, word.capitalize()) for word in constant.split("_"))


def git_head(root: str) -> str:
    """The commit a checkout is at, read from .git without running git;
    "" if `root` is not a checkout."""
    git = os.path.join(root, ".git")
    try:
        with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
            head = f.read().strip()
    except OSError:
        return ""
    if not head.startswith("ref: "):
        return head
    ref = head[len("ref: "):]
    try:
        with open(os.path.join(git, ref), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return _packed_ref(os.path.join(git, "packed-refs"), ref)


def _packed_ref(path: str, ref: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
    except OSError:
        pass
    return ""


class Repo:
    """A local checkout of one decompilation. Subclasses give the paths and
    formats; `land_path`, `matrix_path` and `events_path` are relative to
    the checkout, for notes."""

    name = ""

    def __init__(self, root: str, commit: str = ""):
        self.root = root
        self.commit = commit or git_head(root)

    @property
    def repository(self) -> str:
        return "%s/%s" % (OWNER, self.name)

    def land(self, number: int) -> Tuple[int, ...]:
        return landdata.attributes(self._read(self.land_path(number)))

    def matrix(self, number: int) -> Matrix:
        raise NotImplementedError

    def events(self, spec: str) -> Events:
        raise NotImplementedError

    def land_path(self, number: int) -> str:
        raise NotImplementedError

    def matrix_path(self, number: int) -> str:
        raise NotImplementedError

    def events_path(self, spec: str) -> str:
        raise NotImplementedError

    def map_name(self, constant: str) -> str:
        return display_name(constant)

    def _read(self, relative: str) -> bytes:
        with open(os.path.join(self.root, relative), "rb") as f:
            return f.read()


class Platinum(Repo):
    """pret/pokeplatinum. Events are named by their file's stem after
    "events_" ("route_201"), or by a path."""

    name = "pokeplatinum"

    def land_path(self, number: int) -> str:
        return "res/field/maps/data/map_data_%03d.bin" % number

    def matrix_path(self, number: int) -> str:
        return "res/field/matrices/map_matrix_%03d.json" % number

    def events_path(self, spec: str) -> str:
        if spec.endswith(".json"):
            return spec
        return "res/field/events/events_%s.json" % spec

    def matrix(self, number: int) -> Matrix:
        return landdata.matrix_from_json(json.loads(self._read(self.matrix_path(number)).decode("utf-8")))

    def events(self, spec: str) -> Events:
        return events.events_from_json(json.loads(self._read(self.events_path(spec)).decode("utf-8")))


class Diamond(Repo):
    """pret/pokediamond. Events are named by their narc number ("327")."""

    name = "pokediamond"

    def __init__(self, root: str, commit: str = ""):
        super().__init__(root, commit)
        self._map_ids: Optional[Dict[int, str]] = None
        self._sprites: Optional[Dict[int, str]] = None

    def land_path(self, number: int) -> str:
        return "files/fielddata/land_data/land_data_release/narc_%04d.bin" % number

    def matrix_path(self, number: int) -> str:
        return "files/fielddata/mapmatrix/map_matrix/narc_%04d.bin" % number

    def events_path(self, spec: str) -> str:
        if spec.endswith(".bin"):
            return spec
        return "files/fielddata/eventdata/zone_event_release/narc_%04d.bin" % int(spec)

    def matrix(self, number: int) -> Matrix:
        return landdata.matrix_from_binary(self._read(self.matrix_path(number)), self.map_ids())

    def events(self, spec: str) -> Events:
        return events.events_from_binary(self._read(self.events_path(spec)), self.sprite_names(), self.map_ids())

    def map_ids(self) -> Mapping[int, str]:
        """Map id to constant, from include/constants/maps.h."""
        if self._map_ids is None:
            self._map_ids = self._defines("include/constants/maps.h", "MAP_")
        return self._map_ids

    def sprite_names(self) -> Mapping[int, str]:
        """Sprite id to graphic name (SPRITE_MAN1 is "MAN1"), from
        include/constants/sprites.h plus the signposts it leaves unnamed."""
        if self._sprites is None:
            names = dict(DIAMOND_SPRITE_NAMES)
            for number, constant in self._defines("include/constants/sprites.h", "SPRITE_").items():
                names[number] = constant[len("SPRITE_"):]
            self._sprites = names
        return self._sprites

    def _defines(self, relative: str, prefix: str) -> Dict[int, str]:
        values: Dict[int, str] = {}
        for line in self._read(relative).decode("utf-8").splitlines():
            match = _DEFINE.match(line)
            if match and match.group(1).startswith(prefix):
                values.setdefault(int(match.group(2)), match.group(1))
        return values


REPOS = {Platinum.name: Platinum, Diamond.name: Diamond}


def open_repo(kind: str, root: str, commit: str = "") -> Repo:
    """A Repo of `kind` ("pokeplatinum" or "pokediamond") at `root`."""
    if kind not in REPOS:
        raise ValueError("unknown repository %r; one of %s" % (kind, sorted(REPOS)))
    return REPOS[kind](root, commit)
