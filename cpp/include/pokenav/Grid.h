/*  PokemonNavigation - Grid
 *
 *  Tiles and directions on an overworld grid, shared by the games that
 *  move the player a tile at a time.
 *
 *  Ported from Arduino-Source (MIT): SerialPrograms/Source/Pokemon/Navigation/Pokemon_Grid.h
 */

#ifndef POKENAV_GRID_H
#define POKENAV_GRID_H

#include <cstddef>
#include <functional>
#include <string>

namespace pokenav{


//  Row 0 is the top of a map, so SOUTH increases y.
enum class Direction{
    NORTH,
    EAST,
    SOUTH,
    WEST,
};
constexpr Direction ALL_DIRECTIONS[] = {
    Direction::NORTH, Direction::EAST, Direction::SOUTH, Direction::WEST,
};
const char* direction_name(Direction direction);
Direction opposite(Direction direction);


struct TilePos{
    int x = 0;
    int y = 0;

    TilePos next(Direction direction) const;
    bool operator==(const TilePos& other) const{ return x == other.x && y == other.y; }
    bool operator!=(const TilePos& other) const{ return !(*this == other); }
};
std::string to_string(const TilePos& pos);



}


template <>
struct std::hash<pokenav::TilePos>{
    size_t operator()(const pokenav::TilePos& pos) const{
        return std::hash<long long>()(((long long)pos.x << 32) ^ (unsigned)pos.y);
    }
};


#endif
