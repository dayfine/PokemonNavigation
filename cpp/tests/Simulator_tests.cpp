/*  PokemonNavigation - Simulator tests
 *
 *  The movement rules of Arduino-Source's bdsp/grid-sim SimJubilife, on a
 *  small room and on its hand-made grid of the Poketch Company's corner
 *  (games/bdsp/maps/sim_poketch_company.txt).
 */

#include <string>
#include <vector>
#include "pokenav/Simulator.h"
#include "pokenav/TileGrid.h"
#include "TestRunner.h"

namespace pokenav{
namespace test{


namespace{

const TileGrid& room(){
    static const TileGrid grid({
        R"(#######)",
        R"(#.....#)",
        R"(#.....#)",
        R"(#.....#)",
        R"(#######)",
    });
    return grid;
}

const TileGrid& poketch_company(){
    static const TileGrid grid = TileGrid::load(games_dir() + "/bdsp/maps/sim_poketch_company.txt");
    return grid;
}
const TilePos LONG_ROAD_EAST_END{24, 7};
const TilePos GAP{9, 5};

Result test_turns_and_taps(){
    const PhysicsModel physics;
    Simulator sim(room(), physics, {1, 1}, Direction::SOUTH, 1);
    sim.turn(Direction::EAST);
    if (!(sim.position() == TilePos{1, 1}) || sim.facing() != Direction::EAST){
        return "A turn toward another way moved us.";
    }
    sim.turn(Direction::EAST);
    if (!(sim.position() == TilePos{2, 1}) || sim.turn_steps() != 1){
        return "A turn toward the way we face should step (turn_when_facing_steps).";
    }
    if (sim.taps(Direction::EAST, 2) != 2 || !(sim.position() == TilePos{4, 1})){
        return "Two taps should be two tiles with no extra chance.";
    }
    if (sim.taps(Direction::EAST, 5) != 1){
        return "Taps should stop at the wall.";
    }
    if (sim.clock_ms() != 400 + 400 + 2 * 560 + 800 + 5 * 560 + 800){
        return "Clock is " + std::to_string(sim.clock_ms()) + " ms.";
    }
    PhysicsModel no_turn_step;
    no_turn_step.set(physics::TURN_WHEN_FACING_STEPS, 0, ParameterStatus::GUESSED);
    Simulator still(room(), no_turn_step, {1, 1}, Direction::EAST, 1);
    still.turn(Direction::EAST);
    if (!(still.position() == TilePos{1, 1})){
        return "With turn_when_facing_steps 0 a turn should not step.";
    }
    return true;
}

Result test_walk_until_stopped(){
    const PhysicsModel physics;
    Simulator sim(room(), physics, {1, 2}, Direction::EAST, 1);
    const WalkReport east = sim.walk_until_stopped(Direction::EAST, 10);
    if (!east.stopped || east.tiles != 3 || !(sim.position() == TilePos{5, 2})){
        //  The turn tap facing east already stepped one tile.
        return "East to the wall: " + std::to_string(east.tiles) + " tiles to " + to_string(sim.position()) + ".";
    }
    Simulator open(room(), physics, {1, 2}, Direction::NORTH, 1);
    const WalkReport limited = open.walk_until_stopped(Direction::EAST, 2);
    if (limited.stopped || limited.tiles != 2){
        return "A walk with room left should end at its limit.";
    }
    //  A stop seen far too late reads as the limit.
    Simulator late(room(), physics, {1, 2}, Direction::NORTH, 1);
    const WalkReport lagged = late.walk_until_stopped(Direction::EAST, 4, 1000.0);
    if (lagged.stopped){
        return "A stop seen 1000 tiles late should read as the limit.";
    }
    return true;
}

Result test_wanderer_blocks(){
    const PhysicsModel physics;
    Simulator sim(room(), physics, {1, 2}, Direction::NORTH, 3);
    sim.add_wanderer(Wanderer{"npc", {4, 2}, {4, 2}});
    const WalkReport east = sim.walk_until_stopped(Direction::EAST, 10);
    if (!east.stopped || !(sim.position() == TilePos{3, 2})){
        return "The wanderer at (4,2) should stop us at (3,2), not " + to_string(sim.position()) + ".";
    }
    return true;
}

Result test_monte_carlo_robust_plan(){
    //  A plan of walls only is certain; open legs with a chance of an extra
    //  tile are not.
    PhysicsModel physics;
    physics.set(physics::TAP_EXTRA_TILE_CHANCE, 0.3, ParameterStatus::GUESSED);
    const auto make = [&](uint64_t seed){ return Simulator(room(), physics, {3, 2}, Direction::NORTH, seed); };

    const auto walls = plan_robust_route(room(), {3, 2}, {1, 1});
    if (!walls){
        return "No robust plan to the corner.";
    }
    const MonteCarloStats corner = run_monte_carlo(make,
        [&](Simulator& sim){ return play_planned_legs(sim, *walls); }, 200, 1);
    log("room, to the corner: " + corner.to_string());
    if (corner.successes != corner.runs){
        return "A plan of wall legs failed: " + corner.to_string();
    }

    RobustPlanCosts exact;
    exact.exact_open_tiles = 2;
    const auto open = plan_robust_route(room(), {1, 1}, {3, 1}, exact);
    if (!open){
        return "No plan with an open leg.";
    }
    const auto make_corner = [&](uint64_t seed){ return Simulator(room(), physics, {1, 1}, Direction::NORTH, seed); };
    const MonteCarloStats taps = run_monte_carlo(make_corner,
        [&](Simulator& sim){ return play_planned_legs(sim, *open); }, 500, 1);
    log("room, two taps east: " + taps.to_string());
    if (taps.successes == 0 || taps.successes == taps.runs || taps.failures.empty()){
        return "Taps with a 30% extra tile should sometimes miss: " + taps.to_string();
    }
    const MonteCarloStats again = run_monte_carlo(make_corner,
        [&](Simulator& sim){ return play_planned_legs(sim, *open); }, 500, 1);
    if (again.successes != taps.successes || again.mean_ms != taps.mean_ms){
        return "The same seeds gave another result.";
    }
    return true;
}

Result test_poketch_company(){
    //  From the long road's east end to the gap beside the sign, with the
    //  clown wandering in the plaza and the gap's row, on the BDSP physics.
    const TileGrid& grid = poketch_company();
    if (!grid.standable(LONG_ROAD_EAST_END) || !grid.standable(GAP) || grid.at({8, 5}) != TileType::SIGN){
        return "The Poketch Company grid's named tiles are wrong.";
    }
    const PhysicsModel physics = PhysicsModel::load(games_dir() + "/bdsp/physics.txt");
    RobustPlanCosts costs;
    costs.exact_open_tiles = 1;
    const auto legs = plan_robust_route(grid, LONG_ROAD_EAST_END, GAP, costs);
    if (!legs){
        return "No robust plan to the gap.";
    }
    std::string text = "Poketch Company, long road east end to the gap:";
    for (const PlannedLeg& leg : *legs){
        text += "\n    " + to_string(leg);
    }
    log(text);
    const auto make = [&](uint64_t seed){
        Simulator sim(grid, physics, LONG_ROAD_EAST_END, Direction::WEST, seed);
        sim.add_wanderer(Wanderer{"clown", {9, 2}, {11, 5}});
        return sim;
    };
    const MonteCarloStats stats = run_monte_carlo(make,
        [&](Simulator& sim){ return play_planned_legs(sim, *legs); }, 1000, 1);
    log("Poketch Company, 1000 runs: " + stats.to_string());
    if (stats.runs != 1000 || stats.successes == 0 || stats.mean_ms <= 0){
        return "Unexpected Monte Carlo result: " + stats.to_string();
    }
    return true;
}

}


void add_tests_Simulator(Database& database){
    database.add("Simulator - turns and taps", test_turns_and_taps);
    database.add("Simulator - walk until stopped", test_walk_until_stopped);
    database.add("Simulator - a wanderer blocks", test_wanderer_blocks);
    database.add("Simulator - Monte Carlo of robust plans", test_monte_carlo_robust_plan);
    database.add("Simulator - BDSP Poketch Company corner", test_poketch_company);
}



}
}
