/*  PokemonNavigation - Map Set
 *
 *  Ported from Arduino-Source (MIT): SerialPrograms/Source/Pokemon/Navigation/Pokemon_MapSet.h
 *
 *  Several tile grids placed side by side on one world grid, so one plan
 *  can cross from a route into a town.
 */

#ifndef POKENAV_MAPSET_H
#define POKENAV_MAPSET_H

#include <optional>
#include <string>
#include <vector>
#include "pokenav/TileGrid.h"

namespace pokenav{


struct MapTile{
    std::string map;
    TilePos pos;
};


class MapSet{
public:
    //  Places `grid` with its tile (0,0) at `offset`. Offsets are relative to
    //  each other and may be negative. Maps may overlap only where both are
    //  blocked; the map placed first holds those tiles. Throws
    //  Error if the name is taken or the maps conflict.
    void add(std::string name, const TileGrid& grid, const TilePos& offset);

    //  The maps joined on one grid. Tiles no map covers are UNKNOWN. World
    //  tile (0,0) is the top-left corner of all the maps together.
    const TileGrid& world() const;

    //  Throws Error for an unknown map name.
    TilePos to_world(const std::string& map, const TilePos& local) const;

    //  The map that holds a world tile, or nothing between maps.
    std::optional<MapTile> to_local(const TilePos& world) const;

    //  "Route 201 (45,3)", or the world tile if no map holds it.
    std::string describe(const TilePos& world) const;

private:
    struct Placed{
        std::string name;
        TileGrid grid;
        TilePos offset;
    };
    std::vector<Placed> m_maps;
    TilePos m_origin;   //  offset of world tile (0,0)
    std::optional<TileGrid> m_world;
};



}
#endif
