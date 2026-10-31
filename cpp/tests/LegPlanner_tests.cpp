/*  PokemonNavigation - Leg Planner Tests
 *
 *  Ported from Arduino-Source (MIT): SerialPrograms/Source/Pokemon/Navigation/Pokemon_LegPlanner_Tests.cpp
 *
 *  The planner on a small made-up game, with the kinds of tiles the real
 *  games have: walls, people, tall grass, a one-way tile and a warp.
 *
 */

#include <functional>
#include <string>
#include <vector>
#include "pokenav/LegPlanner.h"
#include "TestRunner.h"

namespace pokenav{
namespace test{


namespace{

//  '#' wall, '.' floor, '"' tall grass, 'p' a person (blocks, but may walk
//  off, so not a wall to stop against), 'v' entered only going south, 'W'
//  a warp to the tile marked 'X'.
class ToyGame{
public:
    using State = TilePos;
    using StateHash = std::hash<TilePos>;

    explicit ToyGame(std::vector<std::string> rows)
        : m_rows(std::move(rows))
    {
        for (int y = 0; y < (int)m_rows.size(); y++){
            for (int x = 0; x < (int)m_rows[y].size(); x++){
                if (m_rows[y][x] == 'X'){
                    m_warp_to = {x, y};
                }
            }
        }
    }

    std::optional<Step<State>> press(const State& state, Direction direction) const{
        const TilePos next = state.next(direction);
        const char tile = at(next);
        if (tile == '#' || tile == 'p' || (tile == 'v' && direction != Direction::SOUTH)){
            return std::nullopt;
        }
        Step<State> step;
        step.next = next;
        step.facing = direction;
        if (tile == '"'){
            step.extra_cost = 5;
        }
        if (tile == 'W'){
            step.next = m_warp_to;
            step.warped = true;
            step.ends_leg = true;
            step.extra_cost = 10;
        }
        return step;
    }
    bool held_at(const State& state, Direction direction) const{
        const char tile = at(state.next(direction));
        return tile == '#' || (tile == 'v' && direction != Direction::SOUTH);
    }

private:
    char at(const TilePos& pos) const{
        if (pos.y < 0 || pos.y >= (int)m_rows.size() || pos.x < 0 || pos.x >= (int)m_rows[pos.y].size()){
            return '#';
        }
        return m_rows[pos.y][pos.x];
    }

    std::vector<std::string> m_rows;
    TilePos m_warp_to;
};


std::string describe(const std::vector<Leg<TilePos>>& legs){
    std::string text;
    for (const Leg<TilePos>& leg : legs){
        text += "\n  ";
        text += leg.kind == LegKind::FACE ? "face " : "walk ";
        text += direction_name(leg.direction);
        if (leg.kind == LegKind::WALK){
            text += " " + std::to_string(leg.tiles);
        }
        if (leg.to_wall){
            text += " (to wall)";
        }
        if (leg.warps){
            text += " (warp)";
        }
        text += " -> " + to_string(leg.end);
    }
    return text;
}

std::optional<std::vector<Leg<TilePos>>> plan(
    const ToyGame& game, TilePos from, TilePos to,
    std::optional<Direction> start_facing = std::nullopt,
    std::optional<Direction> goal_facing = std::nullopt
){
    return plan_legs(game, from, start_facing, std::function<bool(const TilePos&)>([to](const TilePos& pos){ return pos == to; }), goal_facing);
}


Result test_prefers_wall_legs(){
    //  Two ways of equal length: east then south ends both legs in the open;
    //  south then east ends the last one against the pillar.
    const ToyGame game({
        "......",
        "...#..",
        "......",
    });
    const auto legs = plan(game, {0, 0}, {2, 1});
    if (!legs || legs->size() != 2){
        return "Expected 2 legs:" + (legs ? describe(*legs) : std::string(" none"));
    }
    if ((*legs)[1].direction != Direction::EAST || !(*legs)[1].to_wall){
        return "Expected to end going east into the pillar:" + describe(*legs);
    }
    return true;
}

Result test_person_is_not_a_wall(){
    //  The only way ends next to a person, which isn't a wall to stop against.
    const ToyGame game({
        "#####",
        "#..p#",
        "#####",
    });
    const auto legs = plan(game, {1, 1}, {2, 1});
    if (!legs || legs->size() != 1 || (*legs)[0].to_wall){
        return "Expected one open leg:" + (legs ? describe(*legs) : std::string(" none"));
    }
    return true;
}

Result test_avoids_grass(){
    //  Straight through the grass is 4 tiles; around it is 8, cheaper with
    //  5 extra per grass tile.
    const ToyGame game({
        ".....",
        ".\"\"\".",
        ".....",
    });
    const auto legs = plan(game, {0, 1}, {4, 1});
    if (!legs){
        return "No route.";
    }
    for (const Leg<TilePos>& leg : *legs){
        if (leg.end.y == 1 && leg.end.x > 0 && leg.end.x < 4){
            return "Walked into the grass:" + describe(*legs);
        }
    }
    return true;
}

Result test_one_way_tile(){
    //  The 'v' can only be entered going south, so going back up must go around.
    const ToyGame game({
        "#.#.#",
        "#v#.#",
        "#...#",
        "#####",
    });
    if (!plan(game, {1, 0}, {1, 2})){
        return "No route down through the one-way tile.";
    }
    const auto up = plan(game, {1, 2}, {1, 0});
    if (up){
        return "Went up through the one-way tile:" + describe(*up);
    }
    return true;
}

Result test_warp_ends_leg(){
    //  The warp on the left takes the player to X on the right.
    const ToyGame game({
        "#######",
        "#W.#X.#",
        "#..#..#",
        "#######",
    });
    const auto legs = plan(game, {2, 2}, {5, 2});
    if (!legs){
        return "No route.";
    }
    bool warped = false;
    for (const Leg<TilePos>& leg : *legs){
        if (leg.warps){
            warped = true;
            if (!(leg.end == TilePos{4, 1})){
                return "The warp leg ends at " + to_string(leg.end) + ":" + describe(*legs);
            }
        }
    }
    if (!warped){
        return "Expected a warp leg:" + describe(*legs);
    }
    return true;
}

Result test_goal_facing(){
    const ToyGame game({
        "....",
    });
    const auto legs = plan(game, {0, 0}, {2, 0}, std::nullopt, Direction::NORTH);
    if (!legs || legs->back().kind != LegKind::FACE || legs->back().direction != Direction::NORTH){
        return "Expected to end facing north:" + (legs ? describe(*legs) : std::string(" none"));
    }
    return true;
}

Result test_unreachable(){
    const ToyGame game({
        ".#.",
    });
    if (plan(game, {0, 0}, {2, 0})){
        return "Planned through a wall.";
    }
    return true;
}



}


void add_tests_LegPlanner(Database& database){
    database.add("LegPlanner - prefers legs that end at a wall", test_prefers_wall_legs);
    database.add("LegPlanner - a person is not a wall", test_person_is_not_a_wall);
    database.add("LegPlanner - avoids tall grass", test_avoids_grass);
    database.add("LegPlanner - one-way tile", test_one_way_tile);
    database.add("LegPlanner - a warp ends the leg", test_warp_ends_leg);
    database.add("LegPlanner - turns to face the goal", test_goal_facing);
    database.add("LegPlanner - nothing through a wall", test_unreachable);
}



}
}
