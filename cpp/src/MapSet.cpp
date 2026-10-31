/*  PokemonNavigation - Map Set
 *
 *  Ported from Arduino-Source (MIT): SerialPrograms/Source/Pokemon/Navigation/Pokemon_MapSet.cpp
 *
 */

#include <algorithm>
#include "pokenav/Error.h"
#include "pokenav/MapSet.h"

namespace pokenav{


void MapSet::add(std::string name, const TileGrid& grid, const TilePos& offset){
    for (const Placed& placed : m_maps){
        if (placed.name == name){
            throw Error("Map placed twice: " + name);
        }
        //  Map images show a border of trees past their edges, so two maps
        //  may share blocked tiles, but nothing else.
        for (int y = 0; y < grid.height(); y++){
            for (int x = 0; x < grid.width(); x++){
                const TilePos other{offset.x + x - placed.offset.x, offset.y + y - placed.offset.y};
                if (!placed.grid.in_bounds(other)){
                    continue;
                }
                if (grid.at({x, y}) != TileType::BLOCKED || placed.grid.at(other) != TileType::BLOCKED){
                    throw Error("Map " + name + " overlaps " + placed.name + " at its tile " + to_string(TilePos{x, y}) + ".");
                }
            }
        }
    }
    m_maps.push_back(Placed{std::move(name), grid, offset});

    //  Rebuild the joined grid.
    TilePos low = m_maps[0].offset;
    TilePos high = low;
    for (const Placed& placed : m_maps){
        low.x = std::min(low.x, placed.offset.x);
        low.y = std::min(low.y, placed.offset.y);
        high.x = std::max(high.x, placed.offset.x + placed.grid.width());
        high.y = std::max(high.y, placed.offset.y + placed.grid.height());
    }
    m_origin = low;
    std::vector<std::string> rows(high.y - low.y, std::string(high.x - low.x, tile_char(TileType::UNKNOWN)));
    for (const Placed& placed : m_maps){
        const std::vector<std::string> map_rows = placed.grid.rows();
        for (size_t y = 0; y < map_rows.size(); y++){
            rows[placed.offset.y - low.y + y].replace(placed.offset.x - low.x, map_rows[y].size(), map_rows[y]);
        }
    }
    m_world.emplace(rows);
}

const TileGrid& MapSet::world() const{
    if (!m_world){
        throw Error("No maps placed.");
    }
    return *m_world;
}

TilePos MapSet::to_world(const std::string& map, const TilePos& local) const{
    for (const Placed& placed : m_maps){
        if (placed.name == map){
            return {
                placed.offset.x - m_origin.x + local.x,
                placed.offset.y - m_origin.y + local.y,
            };
        }
    }
    throw Error("Unknown map: " + map);
}

std::optional<MapTile> MapSet::to_local(const TilePos& world) const{
    for (const Placed& placed : m_maps){
        const TilePos local{
            world.x + m_origin.x - placed.offset.x,
            world.y + m_origin.y - placed.offset.y,
        };
        if (placed.grid.in_bounds(local)){
            return MapTile{placed.name, local};
        }
    }
    return std::nullopt;
}

std::string MapSet::describe(const TilePos& world) const{
    const std::optional<MapTile> local = to_local(world);
    if (!local){
        return "world " + to_string(world);
    }
    return local->map + " " + to_string(local->pos);
}



}
