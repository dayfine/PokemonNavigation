/*  PokemonNavigation - Tile Grid
 *
 *  Ported from Arduino-Source (MIT): SerialPrograms/Source/Pokemon/Navigation/Pokemon_TileGrid.cpp
 *
 */

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <limits>
#include <map>
#include <queue>
#include <sstream>
#include <tuple>
#include "pokenav/Error.h"
#include "pokenav/LegPlanner.h"
#include "pokenav/TileGrid.h"

namespace pokenav{


char tile_char(TileType type){
    switch (type){
    case TileType::BLOCKED:     return '#';
    case TileType::WALKABLE:    return '.';
    case TileType::TALL_GRASS:  return '"';
    case TileType::LEDGE:       return 'v';
    case TileType::NPC:         return 'N';
    case TileType::SIGN:        return 'S';
    case TileType::DOOR:        return 'D';
    case TileType::UNKNOWN:     return '?';
    }
    return '?';
}




TileGrid::TileGrid(const std::vector<std::string>& rows)
    : m_width(rows.empty() ? 0 : (int)rows[0].size())
    , m_height((int)rows.size())
{
    m_tiles.reserve((size_t)m_width * m_height);
    for (size_t y = 0; y < rows.size(); y++){
        const std::string& row = rows[y];
        if ((int)row.size() != m_width){
            throw Error("Tile grid row " + std::to_string(y) + " has " + std::to_string(row.size()) +
                " tiles, expected " + std::to_string(m_width) + ".");
        }
        for (size_t x = 0; x < row.size(); x++){
            switch (row[x]){
            case '#':   m_tiles.push_back(TileType::BLOCKED);       break;
            case '.':   m_tiles.push_back(TileType::WALKABLE);      break;
            case '"':   m_tiles.push_back(TileType::TALL_GRASS);    break;
            case 'v':   m_tiles.push_back(TileType::LEDGE);         break;
            case 'N':   m_tiles.push_back(TileType::NPC);           break;
            case 'S':   m_tiles.push_back(TileType::SIGN);          break;
            case 'D':   m_tiles.push_back(TileType::DOOR);          break;
            case '?':   m_tiles.push_back(TileType::UNKNOWN);       break;
            default:
                throw Error(std::string("Unknown tile '") + row[x] + "' at " +
                    to_string(TilePos{(int)x, (int)y}) + ".");
            }
        }
    }
}

TileGrid TileGrid::parse(const std::string& text){
    std::vector<std::string> rows;
    std::istringstream lines(text);
    std::string line;
    while (std::getline(lines, line)){
        std::istringstream words(line);
        std::string row;
        if (!(words >> row) || row.compare(0, 2, "//") == 0){
            continue;
        }
        rows.push_back(row);
    }
    return TileGrid(rows);
}

TileGrid TileGrid::load(const std::string& path){
    std::ifstream file(path);
    if (!file){
        throw Error("Cannot read tile grid file: " + path);
    }
    std::ostringstream text;
    text << file.rdbuf();
    return parse(text.str());
}

std::vector<std::string> TileGrid::rows() const{
    std::vector<std::string> rows;
    for (int y = 0; y < m_height; y++){
        std::string row;
        for (int x = 0; x < m_width; x++){
            row += tile_char(at({x, y}));
        }
        rows.push_back(std::move(row));
    }
    return rows;
}

bool TileGrid::in_bounds(const TilePos& pos) const{
    return 0 <= pos.x && pos.x < m_width && 0 <= pos.y && pos.y < m_height;
}

TileType TileGrid::at(const TilePos& pos) const{
    if (!in_bounds(pos)){
        return TileType::UNKNOWN;
    }
    return m_tiles[(size_t)pos.y * m_width + pos.x];
}

void TileGrid::set(const TilePos& pos, TileType type){
    if (in_bounds(pos)){
        m_tiles[(size_t)pos.y * m_width + pos.x] = type;
    }
}

bool TileGrid::standable(const TilePos& pos) const{
    const TileType type = at(pos);
    return type == TileType::WALKABLE || type == TileType::TALL_GRASS;
}

std::optional<TilePos> TileGrid::step(const TilePos& from, Direction direction) const{
    const TilePos next = from.next(direction);
    if (standable(next)){
        return next;
    }
    if (at(next) == TileType::LEDGE && direction == Direction::SOUTH){
        const TilePos landing = next.next(direction);
        if (standable(landing)){
            return landing;
        }
    }
    return std::nullopt;
}

bool TileGrid::at_wall(const TilePos& pos, Direction direction) const{
    const TileType next = at(pos.next(direction));
    return next != TileType::DOOR && next != TileType::UNKNOWN && !step(pos, direction).has_value();
}



WallHit walk_to_wall(const TileGrid& grid, const TilePos& from, Direction direction){
    WallHit hit;
    hit.stop = from;
    while (true){
        const TilePos before = hit.stop;
        const std::optional<TilePos> next = grid.step(before, direction);
        if (!next){
            hit.wall = before.next(direction);
            hit.anchored = grid.at_wall(before, direction);
            return hit;
        }
        hit.tiles += std::abs(next->x - before.x) + std::abs(next->y - before.y);
        hit.stop = *next;
    }
}



std::string to_string(const TileLeg& leg){
    return std::string(direction_name(leg.direction)) + " " + std::to_string(leg.tiles) +
        (leg.ends_at_wall ? " (to wall)" : " (open)");
}


namespace{

//  The grid's step rules for the shared leg planner. A ledge hop is one
//  press that moves two tiles.
class TileGridModel{
public:
    using State = TilePos;
    using StateHash = std::hash<TilePos>;

    TileGridModel(const TileGrid& grid, const TilePlanCosts& costs)
        : m_grid(grid)
        , m_costs(costs)
    {}

    std::optional<Step<State>> press(const State& pos, Direction direction) const{
        const std::optional<TilePos> next = m_grid.step(pos, direction);
        if (!next){
            return std::nullopt;
        }
        Step<State> step;
        step.next = *next;
        step.facing = direction;
        const int tiles = std::abs(next->x - pos.x) + std::abs(next->y - pos.y);
        step.extra_cost = m_costs.per_tile * (tiles - 1);
        if (m_grid.at(*next) == TileType::TALL_GRASS){
            step.extra_cost += m_costs.per_grass_tile;
        }
        return step;
    }
    bool held_at(const State& pos, Direction direction) const{
        return m_grid.at_wall(pos, direction);
    }

private:
    const TileGrid& m_grid;
    const TilePlanCosts& m_costs;
};

}

std::optional<std::vector<TileLeg>> plan_tile_route(
    const TileGrid& grid,
    const TilePos& from, const TilePos& to,
    const TilePlanCosts& costs
){
    if (!grid.standable(from) || !grid.standable(to)){
        throw Error("Route ends must be standable: " + to_string(from) + " -> " + to_string(to) + ".");
    }
    if (from == to){
        return std::vector<TileLeg>();
    }
    LegCosts leg_costs;
    leg_costs.per_tile = costs.per_tile;
    leg_costs.per_turn = costs.per_leg;
    leg_costs.per_open_stop = costs.leg_not_at_wall;
    const std::optional<std::vector<Leg<TilePos>>> legs = plan_legs(
        TileGridModel(grid, costs), from, std::nullopt,
        std::function<bool(const TilePos&)>([&](const TilePos& pos){ return pos == to; }),
        std::nullopt, leg_costs
    );
    if (!legs){
        return std::nullopt;
    }
    std::vector<TileLeg> ret;
    for (const Leg<TilePos>& leg : *legs){
        const size_t tiles = std::abs(leg.end.x - leg.start.x) + std::abs(leg.end.y - leg.start.y);
        ret.push_back(TileLeg{leg.direction, tiles, leg.to_wall});
    }
    return ret;
}

std::vector<TilePos> sight_tiles(const TileGrid& grid, const TrainerSight& trainer){
    std::vector<TilePos> tiles;
    TilePos pos = trainer.pos;
    for (int i = 0; i < trainer.range; i++){
        pos = pos.next(trainer.facing);
        if (!grid.standable(pos)){
            break;
        }
        tiles.push_back(pos);
    }
    return tiles;
}

std::vector<std::vector<std::string>> legs_crossing_sight(
    const TileGrid& grid,
    const TilePos& from,
    const std::vector<TileLeg>& legs,
    const std::vector<TrainerSight>& trainers
){
    std::vector<std::vector<TilePos>> sights;
    for (const TrainerSight& trainer : trainers){
        sights.push_back(sight_tiles(grid, trainer));
    }
    std::vector<std::vector<std::string>> crossings;
    TilePos pos = from;
    for (const TileLeg& leg : legs){
        const std::vector<TilePos> tiles = trace_legs(grid, pos, {leg});
        std::vector<std::string> seen_by;
        for (size_t t = 0; t < trainers.size(); t++){
            for (size_t i = 1; i < tiles.size(); i++){
                if (std::find(sights[t].begin(), sights[t].end(), tiles[i]) != sights[t].end()){
                    seen_by.push_back(trainers[t].name);
                    break;
                }
            }
        }
        crossings.push_back(std::move(seen_by));
        pos = tiles.back();
    }
    return crossings;
}

std::vector<TilePos> trace_legs(
    const TileGrid& grid,
    const TilePos& from,
    const std::vector<TileLeg>& legs
){
    std::vector<TilePos> tiles{from};
    for (const TileLeg& leg : legs){
        size_t travelled = 0;
        while (travelled < leg.tiles){
            const TilePos pos = tiles.back();
            const std::optional<TilePos> next = grid.step(pos, leg.direction);
            if (!next){
                throw Error("Leg " + to_string(leg) + " is stopped at " + to_string(pos) + ".");
            }
            travelled += std::abs(next->x - pos.x) + std::abs(next->y - pos.y);
            tiles.push_back(*next);
        }
        if (travelled != leg.tiles){
            throw Error("Leg " + to_string(leg) + " overshoots on a ledge hop.");
        }
    }
    return tiles;
}



std::string to_string(const PlannedLeg& leg){
    std::string out = to_string(leg.leg) + " to";
    for (const TilePos& pos : leg.after){
        out += " " + to_string(pos);
    }
    return out;
}

namespace{

//  Where `from` ends up after `tiles` steps in `direction`, stopping early at
//  anything that stops the player. Nothing if a step would leave the map or
//  enter a door: the plan cannot tell what happens then.
std::optional<TilePos> step_tiles(
    const TileGrid& grid, TilePos from, Direction direction, int tiles, int& grass
){
    int travelled = 0;
    while (travelled < tiles){
        const std::optional<TilePos> next = grid.step(from, direction);
        if (!next){
            if (!grid.at_wall(from, direction)){
                return std::nullopt;
            }
            break;
        }
        travelled += std::abs(next->x - from.x) + std::abs(next->y - from.y);
        if (grid.at(*next) == TileType::TALL_GRASS){
            grass++;
        }
        from = *next;
    }
    return from;
}

using Spread = std::vector<TilePos>;

bool spread_less(const TilePos& a, const TilePos& b){
    return a.y != b.y ? a.y < b.y : a.x < b.x;
}
void normalize(Spread& spread){
    std::sort(spread.begin(), spread.end(), spread_less);
    spread.erase(std::unique(spread.begin(), spread.end()), spread.end());
}
struct SpreadLess{
    bool operator()(const Spread& a, const Spread& b) const{
        return std::lexicographical_compare(a.begin(), a.end(), b.begin(), b.end(), spread_less);
    }
};

}

std::optional<std::vector<PlannedLeg>> plan_robust_route(
    const TileGrid& grid,
    const TilePos& from, const TilePos& to,
    const RobustPlanCosts& costs
){
    if (!grid.standable(from) || !grid.standable(to)){
        throw Error("Route ends must be standable: " + to_string(from) + " -> " + to_string(to) + ".");
    }
    return plan_robust_route(grid, std::vector<TilePos>{from}, [&](const TilePos& pos){ return pos == to; }, costs);
}

std::optional<std::vector<PlannedLeg>> plan_robust_route(
    const TileGrid& grid,
    const std::vector<TilePos>& from, const std::function<bool(const TilePos&)>& goal,
    const RobustPlanCosts& costs
){
    for (const TilePos& pos : from){
        if (!grid.standable(pos)){
            throw Error("Route starts must be standable: " + to_string(pos) + ".");
        }
    }
    //  Only the start may be wider than costs.max_spread: every leg must bring
    //  the player within it.
    const size_t max_spread = costs.max_spread;
    auto reached = [&](const Spread& spread){
        return std::all_of(spread.begin(), spread.end(), goal);
    };

    struct Node{
        long long cost;
        Spread parent;
        PlannedLeg leg;
        bool done = false;
    };
    std::map<Spread, Node, SpreadLess> nodes;
    using Entry = std::pair<long long, Spread>;
    auto entry_greater = [](const Entry& a, const Entry& b){ return a.first > b.first; };
    std::priority_queue<Entry, std::vector<Entry>, decltype(entry_greater)> queue(entry_greater);

    Spread start = from;
    normalize(start);
    nodes[start] = Node{0, {}, {}};
    queue.emplace(0, start);

    auto relax = [&](const Spread& spread, long long cost, Spread next, PlannedLeg leg){
        normalize(next);
        if (next.size() > max_spread || next == spread){
            return;
        }
        auto iter = nodes.find(next);
        if (iter != nodes.end() && iter->second.cost <= cost){
            return;
        }
        leg.after = next;
        nodes[next] = Node{cost, spread, std::move(leg)};
        queue.emplace(cost, std::move(next));
    };

    while (!queue.empty()){
        const Entry top = queue.top();
        queue.pop();
        const long long cost = top.first;
        const Spread& spread = top.second;
        Node& node = nodes[spread];
        if (node.done || node.cost != cost){
            continue;
        }
        node.done = true;
        if (reached(spread)){
            std::vector<PlannedLeg> legs;
            for (Spread at = spread; at != start; ){
                const Node& step = nodes[at];
                legs.push_back(step.leg);
                at = step.parent;
            }
            std::reverse(legs.begin(), legs.end());
            return legs;
        }

        for (Direction direction : ALL_DIRECTIONS){
            //  To the wall: every position walks until stopped.
            {
                Spread next;
                size_t longest = 0;
                int grass = 0;
                bool ok = true;
                for (const TilePos& pos : spread){
                    const WallHit hit = walk_to_wall(grid, pos, direction);
                    if (!hit.anchored){
                        ok = false;
                        break;
                    }
                    int leg_grass = 0;
                    step_tiles(grid, pos, direction, (int)hit.tiles, leg_grass);
                    grass = std::max(grass, leg_grass);
                    longest = std::max(longest, hit.tiles);
                    next.push_back(hit.stop);
                }
                if (ok && longest > 0){
                    const long long step = (long long)costs.per_leg +
                        (long long)costs.per_tile * longest + (long long)costs.per_grass_tile * grass;
                    relax(spread, cost + step, std::move(next), PlannedLeg{TileLeg{direction, longest, true}, {}});
                }
            }
            //  Open: about `tiles` tiles, give or take `open_error`.
            for (int tiles = 1; tiles <= costs.max_open_tiles; tiles++){
                Spread next;
                int grass = 0;
                bool ok = true;
                for (const TilePos& pos : spread){
                    const int error = tiles <= costs.exact_open_tiles ? 0 : costs.open_error + tiles / costs.open_error_per;
                    for (int n = std::max(1, tiles - error); n <= tiles + error; n++){
                        int leg_grass = 0;
                        const std::optional<TilePos> end = step_tiles(grid, pos, direction, n, leg_grass);
                        if (!end){
                            ok = false;
                            break;
                        }
                        grass = std::max(grass, leg_grass);
                        next.push_back(*end);
                    }
                    if (!ok){
                        break;
                    }
                }
                if (!ok){
                    break;
                }
                const long long step = (long long)costs.per_leg + costs.leg_not_at_wall +
                    (long long)(costs.per_tile + costs.per_open_tile) * tiles + (long long)costs.per_grass_tile * grass;
                relax(spread, cost + step, std::move(next), PlannedLeg{TileLeg{direction, (size_t)tiles, false}, {}});
            }
        }
    }

    return std::nullopt;
}



}
