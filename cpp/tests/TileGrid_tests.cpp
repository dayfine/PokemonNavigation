/*  PokemonNavigation - Tile Grid, Map Set and robust planner tests
 *
 *  Ported from Arduino-Source (MIT):
 *  SerialPrograms/Source/PokemonBDSP/Programs/AutoStory/PokemonBDSP_AutoStory_Tests.cpp
 *  (tile grid parse, wall hit, plans), keeping the game-agnostic cases and
 *  Route 202's console-measured wall hits, with Route 202 read from
 *  games/bdsp/maps/route202.txt. The robust planner cases are new.
 */

#include <algorithm>
#include <cstdlib>
#include <functional>
#include <optional>
#include <string>
#include <vector>
#include "pokenav/Error.h"
#include "pokenav/MapSet.h"
#include "pokenav/TileGrid.h"
#include "TestRunner.h"

namespace pokenav{
namespace test{


namespace{

//  A small map with every tile type.
//  Row 2 is a ledge with a gap at x = 4. The bottom row has a sign at (1,4),
//  an NPC at (3,4) and a door at (5,4); (3,0) is off the map.
const TileGrid& small_grid(){
    static const TileGrid grid({
        R"(#..?..#)",
        R"(#.."".#)",
        R"(#vvv..#)",
        R"(#.....#)",
        R"(#S.N.D#)",
    });
    return grid;
}

const TileGrid& route202(){
    static const TileGrid grid = TileGrid::load(games_dir() + "/bdsp/maps/route202.txt");
    return grid;
}
const TilePos ROUTE202_CATCH_SPOT{19, 22};
const TilePos ROUTE202_EXIT_JUBILIFE{15, 0};


Result test_parse(){
    const TileGrid& grid = small_grid();
    if (grid.width() != 7 || grid.height() != 5){
        return "Small grid is " + std::to_string(grid.width()) + "x" + std::to_string(grid.height()) + ".";
    }
    struct Case{
        TilePos pos;
        TileType type;
    };
    const Case cases[] = {
        {{0, 0}, TileType::BLOCKED},
        {{1, 0}, TileType::WALKABLE},
        {{3, 1}, TileType::TALL_GRASS},
        {{2, 2}, TileType::LEDGE},
        {{3, 4}, TileType::NPC},
        {{1, 4}, TileType::SIGN},
        {{5, 4}, TileType::DOOR},
        {{3, 0}, TileType::UNKNOWN},
        {{-1, 0}, TileType::UNKNOWN},
        {{7, 4}, TileType::UNKNOWN},
    };
    for (const Case& c : cases){
        if (grid.at(c.pos) != c.type){
            return "Tile " + to_string(c.pos) + " parsed as " + std::to_string((int)grid.at(c.pos)) + ".";
        }
    }
    for (const std::vector<std::string>& bad : {
        std::vector<std::string>{"...", ".."},
        std::vector<std::string>{"..x"},
    }){
        try{
            TileGrid parsed(bad);
            return "A malformed grid was accepted.";
        }catch (Error&){}
    }
    if (grid.rows()[4] != "#S.N.D#"){
        return "Small grid row 4 prints as " + grid.rows()[4] + ".";
    }
    return true;
}

Result test_parse_text(){
    const TileGrid parsed = TileGrid::parse(
        "// a comment\n"
        "\n"
        "#..?..#   //  0\n"
        "#..\"\".#\n"
        "#vvv..#\n"
        "#.....#\n"
        "#S.N.D#  // 4\n"
    );
    if (parsed.rows() != small_grid().rows()){
        return "The text form parses to another grid.";
    }
    const TileGrid& route = route202();
    if (route.width() != 36 || route.height() != 26){
        return "Route 202 is " + std::to_string(route.width()) + "x" + std::to_string(route.height()) + ".";
    }
    if (route.at(ROUTE202_CATCH_SPOT) != TileType::TALL_GRASS || route.at({7, 11}) != TileType::NPC){
        return "Route 202's named tiles have the wrong types.";
    }
    try{
        TileGrid::load(games_dir() + "/no_such_map.txt");
        return "A missing file loaded.";
    }catch (Error&){}
    return true;
}

Result test_map_set(){
    MapSet maps;
    maps.add("a", small_grid(), {0, 0});
    maps.add("b", small_grid(), {6, 4});    //  shares one blocked tile
    try{
        maps.add("c", small_grid(), {5, 4});
        return "Maps that overlap on a door were accepted.";
    }catch (Error&){}
    try{
        maps.add("a", small_grid(), {20, 20});
        return "A map placed twice was accepted.";
    }catch (Error&){}
    const TileGrid& world = maps.world();
    if (world.width() != 13 || world.height() != 9){
        return "Joined maps are " + std::to_string(world.width()) + "x" + std::to_string(world.height()) + ".";
    }
    const TilePos door = maps.to_world("b", {5, 4});
    if (!(door == TilePos{11, 8}) || world.at(door) != TileType::DOOR){
        return "b's door is at " + to_string(door) + ".";
    }
    const std::optional<MapTile> local = maps.to_local(door);
    if (!local || local->map != "b" || !(local->pos == TilePos{5, 4})){
        return "b's door does not map back.";
    }
    if (maps.to_local({12, 0}) || world.at({12, 0}) != TileType::UNKNOWN){
        return "A tile between maps belongs to a map.";
    }
    if (maps.describe(door) != "b (5, 4)" || maps.describe({12, 0}) != "world (12, 0)"){
        return "describe() reads " + maps.describe(door) + ".";
    }
    return true;
}

Result test_wall_hit(){
    struct Case{
        const TileGrid& grid;
        TilePos from;
        Direction direction;
        TilePos stop;
        size_t tiles;
        bool anchored;
    };
    const TileGrid& small = small_grid();
    const TileGrid& route = route202();
    const Case cases[] = {
        {small, {1, 1}, Direction::EAST,  {5, 1}, 4, true},     //  through grass to the east wall
        {small, {1, 0}, Direction::SOUTH, {1, 3}, 3, true},     //  hops the ledge, stops at the sign
        {small, {2, 3}, Direction::NORTH, {2, 3}, 0, true},     //  a ledge stops a north walk
        {small, {3, 3}, Direction::SOUTH, {3, 3}, 0, true},     //  the NPC is a wall
        {small, {4, 4}, Direction::NORTH, {4, 0}, 4, false},    //  through the gap, off the top edge
        {small, {4, 3}, Direction::EAST,  {5, 3}, 1, true},
        {small, {4, 4}, Direction::EAST,  {4, 4}, 0, false},    //  into the door
        {small, {2, 0}, Direction::EAST,  {2, 0}, 0, false},    //  off the map
        {route, ROUTE202_CATCH_SPOT, Direction::WEST,  {3, 22}, 16, true},
        {route, ROUTE202_CATCH_SPOT, Direction::NORTH, {19, 20}, 2, true},
        {route, ROUTE202_CATCH_SPOT, Direction::EAST,  {30, 22}, 11, true},
        //  Measured on the console from the post-catch save.
        {route, {30, 22}, Direction::NORTH, {30, 19}, 3, true},
        {route, {30, 19}, Direction::WEST,  {22, 19}, 8, true},
        {route, {22, 19}, Direction::SOUTH, {22, 24}, 5, true},
        {route, {7, 12}, Direction::NORTH, {7, 12}, 0, true},   //  trainer_a holds the player
        //  After trainer_d, as measured in r75: the east wall is at column 31
        //  on row 16, and column 30 is open up to the trees above row 4.
        {route, {22, 16}, Direction::EAST,  {30, 16}, 8, true},
        {route, {30, 16}, Direction::NORTH, {30, 4}, 12, true},
        //  Through the gap east of the north ledge, over the south ledge
        //  and off the bottom edge to Sandgem Town.
        {route, {29, 4}, Direction::SOUTH, {29, 25}, 21, false},
        {route, {12, 8}, Direction::SOUTH, {12, 22}, 14, true}, //  hops both ledges
        {route, ROUTE202_EXIT_JUBILIFE, Direction::NORTH, ROUTE202_EXIT_JUBILIFE, 0, false},
    };
    for (const Case& c : cases){
        const WallHit hit = walk_to_wall(c.grid, c.from, c.direction);
        if (!(hit.stop == c.stop) || hit.tiles != c.tiles || hit.anchored != c.anchored){
            return "Walking " + std::string(direction_name(c.direction)) + " from " +
                to_string(c.from) + " stops at " + to_string(hit.stop) + " after " +
                std::to_string(hit.tiles) + " tiles" + (hit.anchored ? "" : " (not anchored)") +
                ", expected " + to_string(c.stop) + " after " + std::to_string(c.tiles) + ".";
        }
    }
    return true;
}

//  Checks a plan from `from` to `to`: every leg can be walked, ledges are
//  crossed only southward, and each leg's wall flag matches the grid.
std::string check_plan(
    const std::string& name,
    const TileGrid& grid, const TilePos& from, const TilePos& to,
    const std::vector<TrainerSight>& trainers = {}
){
    const std::optional<std::vector<TileLeg>> legs = plan_tile_route(grid, from, to);
    if (!legs){
        return name + ": no route found.";
    }
    const std::vector<std::vector<std::string>> seen = legs_crossing_sight(grid, from, *legs, trainers);
    std::string text = name + ": from " + to_string(from);
    TilePos end = from;
    for (size_t i = 0; i < legs->size(); i++){
        const TileLeg& leg = (*legs)[i];
        end = trace_legs(grid, end, {leg}).back();
        text += "\n    " + to_string(leg) + " to " + to_string(end);
        for (const std::string& trainer : seen[i]){
            text += ", crosses " + trainer + "'s sight";
        }
    }
    log(text);

    std::vector<TilePos> tiles;
    try{
        tiles = trace_legs(grid, from, *legs);
    }catch (Error& e){
        return name + ": " + e.what();
    }
    if (!(tiles.back() == to)){
        return name + ": the legs end at " + to_string(tiles.back()) + ".";
    }
    for (size_t i = 1; i < tiles.size(); i++){
        const TilePos& a = tiles[i - 1];
        const TilePos& b = tiles[i];
        if (!grid.standable(b)){
            return name + ": the route stands on " + to_string(b) + ".";
        }
        const int dx = b.x - a.x;
        const int dy = b.y - a.y;
        if (std::abs(dx) + std::abs(dy) == 1){
            continue;
        }
        if (dx != 0 || dy != 2 || grid.at(a.next(Direction::SOUTH)) != TileType::LEDGE){
            return name + ": jump from " + to_string(a) + " to " + to_string(b) + " is not a south ledge hop.";
        }
    }
    TilePos pos = from;
    for (const TileLeg& leg : *legs){
        if (leg.tiles == 0){
            return name + ": empty leg.";
        }
        pos = trace_legs(grid, pos, {leg}).back();
        if (leg.ends_at_wall != grid.at_wall(pos, leg.direction)){
            return name + ": leg " + to_string(leg) + " has the wrong wall flag.";
        }
    }
    for (size_t i = 1; i < legs->size(); i++){
        if ((*legs)[i].direction == (*legs)[i - 1].direction){
            return name + ": two legs in a row go " + direction_name((*legs)[i].direction) + ".";
        }
    }
    return "";
}

Result test_plans(){
    const TileGrid& small = small_grid();

    //  South over the ledge is a straight hop; back north must use the gap.
    std::string error = check_plan("Small south", small, {2, 0}, {2, 4});
    if (!error.empty()){
        return error;
    }
    error = check_plan("Small north", small, {2, 4}, {2, 0});
    if (!error.empty()){
        return error;
    }
    const auto south = plan_tile_route(small, {2, 0}, {2, 4});
    if (south->size() != 1 || south->front().direction != Direction::SOUTH){
        return "Small south should be one leg over the ledge.";
    }

    //  Walled in by ledges from below.
    const TileGrid pit({
        R"(#.#)",
        R"(#v#)",
        R"(#.#)",
    });
    if (plan_tile_route(pit, {1, 2}, {1, 0})){
        return "A route north over a ledge was found.";
    }

    //  Route 202, from the catch spot to the exit to Jubilife, past the
    //  trainers (whose sight lines are listed, not avoided).
    const std::vector<TrainerSight> trainers = {
        {"trainer_a", {7, 11}, Direction::SOUTH, 4},
        {"trainer_b", {10, 7}, Direction::SOUTH, 4},
    };
    error = check_plan("Route 202 catch spot to Jubilife", route202(), ROUTE202_CATCH_SPOT, ROUTE202_EXIT_JUBILIFE, trainers);
    if (!error.empty()){
        return error;
    }
    try{
        plan_tile_route(small, {0, 0}, {1, 1});
        return "A route from a wall was planned.";
    }catch (Error&){}
    return true;
}

Result test_sight(){
    const TileGrid& small = small_grid();
    const TrainerSight trainer{"npc", {3, 4}, Direction::NORTH, 4};
    //  North of (3,4): (3,3), then the ledge at (3,2) ends the sight.
    const std::vector<TilePos> tiles = sight_tiles(small, trainer);
    if (tiles.size() != 1 || !(tiles[0] == TilePos{3, 3})){
        return "The NPC sees " + std::to_string(tiles.size()) + " tiles.";
    }
    const std::vector<TileLeg> legs = {{Direction::EAST, 4, true}};
    const auto crossing = legs_crossing_sight(small, {1, 3}, legs, {trainer});
    if (crossing.size() != 1 || crossing[0] != std::vector<std::string>{"npc"}){
        return "The leg east along row 3 should cross the NPC's sight.";
    }
    try{
        trace_legs(small, {1, 3}, {{Direction::EAST, 6, false}});
        return "A leg through the east wall was traced.";
    }catch (Error&){}
    return true;
}


std::string describe(const std::vector<PlannedLeg>& legs){
    std::string text;
    for (const PlannedLeg& leg : legs){
        text += "\n    " + to_string(leg);
    }
    return text;
}

//  A walled room, open inside.
const TileGrid& room(){
    static const TileGrid grid({
        R"(#######)",
        R"(#.....#)",
        R"(#.....#)",
        R"(#.....#)",
        R"(#.....#)",
        R"(#######)",
    });
    return grid;
}

Result test_robust_walls_collapse(){
    //  We may be on any tile of the top row; west then north is the corner.
    std::vector<TilePos> from;
    for (int x = 1; x <= 5; x++){
        from.push_back({x, 1});
    }
    const auto legs = plan_robust_route(room(), from, [](const TilePos& pos){ return pos == TilePos{1, 4}; });
    if (!legs){
        return "No robust route to the corner.";
    }
    log("room, top row to (1, 4):" + describe(*legs));
    for (const PlannedLeg& leg : *legs){
        if (!leg.leg.ends_at_wall){
            return "An open leg was used where walls do:" + describe(*legs);
        }
    }
    if (legs->back().after != std::vector<TilePos>{{1, 4}}){
        return "The plan does not end on the corner alone:" + describe(*legs);
    }
    return true;
}

Result test_robust_open_legs_spread(){
    //  The middle of the room can only be reached by an open leg, which may
    //  go a tile short or long: no plan, unless short legs land exactly.
    const auto none = plan_robust_route(room(), {1, 1}, {3, 2});
    if (none){
        return "A robust plan to an open tile was found:" + describe(*none);
    }
    RobustPlanCosts exact;
    exact.exact_open_tiles = 2;
    const auto legs = plan_robust_route(room(), {1, 1}, {3, 2}, exact);
    if (!legs){
        return "No plan with exact short legs.";
    }
    log("room, (1,1) to (3,2) with exact short legs:" + describe(*legs));
    if (legs->back().after != std::vector<TilePos>{{3, 2}}){
        return "The plan ends on more than the goal:" + describe(*legs);
    }

    //  An open leg's spread is reported: east 2 from the west wall may end
    //  a tile either way.
    RobustPlanCosts loose;
    loose.max_spread = 3;
    const auto spread = plan_robust_route(room(), std::vector<TilePos>{{1, 2}},
        [](const TilePos& pos){ return pos.y == 4 && pos.x >= 2 && pos.x <= 4; }, loose);
    if (!spread){
        return "No plan to the bottom row's middle.";
    }
    log("room, (1,2) to the bottom row's middle:" + describe(*spread));
    for (const TilePos& pos : spread->back().after){
        if (pos.y != 4 || pos.x < 2 || pos.x > 4){
            return "The plan may end on " + to_string(pos) + ":" + describe(*spread);
        }
    }
    return true;
}

Result test_robust_avoids_doors_and_edges(){
    //  Walking north from (2,3) would enter the door; the plan must go round
    //  and never use a leg that may run into it.
    const TileGrid grid({
        R"(##D###)",
        R"(#....#)",
        R"(#....#)",
        R"(#....#)",
        R"(######)",
    });
    const auto legs = plan_robust_route(grid, {2, 3}, {1, 1});
    if (!legs){
        return "No robust route.";
    }
    log("door room, (2,3) to (1,1):" + describe(*legs));
    std::vector<TilePos> starts = {{2, 3}};
    for (const PlannedLeg& planned : *legs){
        for (TilePos pos : starts){
            for (int i = 0; i < 10; i++){
                if (grid.at(pos.next(planned.leg.direction)) == TileType::DOOR){
                    return to_string(planned.leg) + " may walk into the door:" + describe(*legs);
                }
                const std::optional<TilePos> step = grid.step(pos, planned.leg.direction);
                if (!step){
                    break;
                }
                pos = *step;
            }
        }
        starts = planned.after;
    }
    if (legs->back().after != std::vector<TilePos>{{1, 1}}){
        return "The plan does not end on (1,1):" + describe(*legs);
    }
    return true;
}

Result test_robust_route202(){
    //  From the catch spot to the save spot under the south ledge, every leg
    //  must bring the possible tiles back to one.
    const auto legs = plan_robust_route(route202(), ROUTE202_CATCH_SPOT, TilePos{30, 19});
    if (!legs){
        return "No robust route on Route 202.";
    }
    log("Route 202, catch spot to save spot:" + describe(*legs));
    if (legs->back().after != std::vector<TilePos>{{30, 19}}){
        return "The plan does not end on the save spot:" + describe(*legs);
    }
    for (const PlannedLeg& leg : *legs){
        if (leg.after.size() > RobustPlanCosts().max_spread){
            return "A leg spreads too far:" + describe(*legs);
        }
    }
    return true;
}

}


void add_tests_TileGrid(Database& database){
    database.add("TileGrid - parse", test_parse);
    database.add("TileGrid - parse text and files", test_parse_text);
    database.add("TileGrid - map set", test_map_set);
    database.add("TileGrid - wall hit", test_wall_hit);
    database.add("TileGrid - plans", test_plans);
    database.add("TileGrid - trainer sight", test_sight);
    database.add("RobustPlanner - walls collapse the possible tiles", test_robust_walls_collapse);
    database.add("RobustPlanner - open legs spread", test_robust_open_legs_spread);
    database.add("RobustPlanner - avoids doors", test_robust_avoids_doors_and_edges);
    database.add("RobustPlanner - Route 202", test_robust_route202);
}



}
}
