"""Maps joined into a world: connections between map edges, and warps.

A `Place` is a tile on a named map. The world answers two questions the
movement rules need when a step leaves a map:

- `across_edge`: walking off an edge that has a connection lands on the
  connected map, shifted by the connection's offset (as in the GBA games'
  map headers);
- `warp_arrival`: entering a warp lands on the warp it leads to. Arriving
  through a door, the player steps out of it (south in the games so far),
  so the arrival tile is the one in front of the door.

Example: Route 1's north edge connects to Viridian City with offset -12,
so the tile past Route 1's (10, 0) is Viridian City's (22, height - 1):

    world = World([route1, viridian])
    world.across_edge(Place("Route 1", Tile(10, -1)))
    # Place(map='Viridian City', tile=Tile(x=22, y=39))
"""

from typing import Dict, Iterable, NamedTuple, Optional

from pokenav.grid.geometry import Direction, Tile
from pokenav.grid.maps.model import Behavior, Cell, GridMap2D, Viewport
from pokenav.grid.maps.schema import Connection, MapFile

#   The way a player walks out of a door they arrive through. Gen 3 and BDSP
#   doors both face south; a game where they do not can pass its own.
DOOR_EXIT = Direction.SOUTH


class Place(NamedTuple):
    """A tile on a named map."""

    map: str
    tile: Tile

    def step(self, direction: Direction, count: int = 1) -> "Place":
        return Place(self.map, self.tile.step(direction, count))

    def __str__(self) -> str:
        return "%s %s" % (self.map, self.tile)


class Arrival(NamedTuple):
    """Where a warp puts the player, and the way they face."""

    place: Place
    facing: Direction


class World:
    """A set of maps by name, with their connections and warps."""

    def __init__(self, maps: Iterable[MapFile] = (), door_exit: Direction = DOOR_EXIT):
        self.maps: Dict[str, MapFile] = {}
        self.door_exit = door_exit
        for map_file in maps:
            self.add(map_file)

    def add(self, map_file: MapFile) -> None:
        if map_file.name in self.maps:
            raise ValueError("map %r is already in the world" % map_file.name)
        self.maps[map_file.name] = map_file

    def grid(self, name: str) -> GridMap2D:
        return self.maps[name].grid

    def at(self, place: Place) -> Optional[Cell]:
        """The cell at `place`, or None if its map is unknown or the tile is
        off that map."""
        map_file = self.maps.get(place.map)
        return map_file.grid.at(place.tile) if map_file else None

    def shows(self, place: Place) -> bool:
        """Whether the game draws a loaded map's tile at `place`: on its map,
        or past an edge onto a connected map that is loaded."""
        if self.at(place) is not None:
            return True
        across = self.across_edge(place)
        return across is not None and self.at(across) is not None

    def off_map_fraction(self, place: Place, viewport: Viewport) -> float:
        """The share of the screen, 0 to 1, that shows no map (black) while
        the player stands on `place`. Connected maps count as shown."""
        window = [Place(place.map, tile) for tile in viewport.window(place.tile)]
        return sum(1 for p in window if not self.shows(p)) / len(window)

    def connection_at(self, beyond: Place) -> Optional[Connection]:
        """The connection a tile just past an edge of its map lies across,
        whether or not the connected map is loaded; None if there is none
        (the edge is a wall)."""
        edge = self.grid(beyond.map).edge_crossed(beyond.tile)
        if edge is None:
            return None
        along = beyond.tile.x if edge.is_vertical else beyond.tile.y
        for connection in self.maps[beyond.map].connections:
            if connection.direction is edge and self._spans(connection, along):
                return connection
        return None

    def across_edge(self, beyond: Place) -> Optional[Place]:
        """The place on a connected, loaded map for a tile just past an edge
        of its map, or None."""
        connection = self.connection_at(beyond)
        if connection is None or connection.map not in self.maps:
            return None
        grid = self.grid(beyond.map)
        edge = grid.edge_crossed(beyond.tile)
        tile = _translate(beyond.tile, edge, grid, self.grid(connection.map), connection.offset)
        return Place(connection.map, tile)

    def warp_arrival(self, place: Place, direction: Direction) -> Optional[Arrival]:
        """Where entering the warp at `place` (walking `direction`) puts the
        player, or None if there is no warp there or its target is not
        loaded."""
        warp = next((w for w in self.maps[place.map].warps if w.tile == place.tile), None)
        if warp is None or warp.to_map not in self.maps:
            return None
        targets = self.maps[warp.to_map].warps
        if not 0 <= warp.to_warp < len(targets):
            raise ValueError("%s: warp to %s #%d, which has %d warps"
                             % (place, warp.to_map, warp.to_warp, len(targets)))
        target = Place(warp.to_map, targets[warp.to_warp].tile)
        if self.at(target).behavior is Behavior.DOOR:
            return Arrival(target.step(self.door_exit), self.door_exit)
        return Arrival(target, direction)

    def _spans(self, connection: Connection, along: int) -> bool:
        """Whether `connection` covers position `along` of its edge. A map
        can have several connections on one edge; one whose map is not
        loaded is taken to cover the whole edge."""
        if connection.map not in self.maps:
            return True
        other = self.grid(connection.map)
        length = other.width if connection.direction.is_vertical else other.height
        return 0 <= along - connection.offset < length


def _translate(tile: Tile, edge: Direction, grid: GridMap2D, other: GridMap2D, offset: int) -> Tile:
    """`tile`, just past `edge` of `grid`, in the coordinates of `other`."""
    if edge is Direction.NORTH:
        return Tile(tile.x - offset, other.height + tile.y)
    if edge is Direction.SOUTH:
        return Tile(tile.x - offset, tile.y - grid.height)
    if edge is Direction.WEST:
        return Tile(other.width + tile.x, tile.y - offset)
    return Tile(tile.x - grid.width, tile.y - offset)
