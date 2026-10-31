/*  PokemonNavigation - Grid
 *
 *  Ported from Arduino-Source (MIT): SerialPrograms/Source/Pokemon/Navigation/Pokemon_Grid.cpp
 */

#include "pokenav/Grid.h"

namespace pokenav{


const char* direction_name(Direction direction){
    switch (direction){
    case Direction::NORTH:
        return "north";
    case Direction::EAST:
        return "east";
    case Direction::SOUTH:
        return "south";
    case Direction::WEST:
        return "west";
    }
    return "?";
}

Direction opposite(Direction direction){
    switch (direction){
    case Direction::NORTH:
        return Direction::SOUTH;
    case Direction::EAST:
        return Direction::WEST;
    case Direction::SOUTH:
        return Direction::NORTH;
    case Direction::WEST:
        return Direction::EAST;
    }
    return direction;
}


TilePos TilePos::next(Direction direction) const{
    switch (direction){
    case Direction::NORTH:
        return {x, y - 1};
    case Direction::EAST:
        return {x + 1, y};
    case Direction::SOUTH:
        return {x, y + 1};
    case Direction::WEST:
        return {x - 1, y};
    }
    return *this;
}

std::string to_string(const TilePos& pos){
    return "(" + std::to_string(pos.x) + ", " + std::to_string(pos.y) + ")";
}



}
