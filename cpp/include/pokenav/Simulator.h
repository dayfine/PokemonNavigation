/*  PokemonNavigation - Movement simulator
 *
 *  Plays movement actions on a tile grid with a stochastic PhysicsModel and a
 *  clock, so a route (or a bot's own code, through an adapter that maps its
 *  actions onto these) runs many times (Monte Carlo) and is scored in
 *  seconds instead of minutes per console run.
 *
 *  Ported and made game-agnostic from Arduino-Source (MIT), branch
 *  bdsp/grid-sim: PokemonBDSP_AutoStory_Sim.{h,cpp} (SimJubilife's movement
 *  and run_monte_carlo()). Talking, signs and the story's checkpoints stay in
 *  the bot.
 */

#ifndef POKENAV_SIMULATOR_H
#define POKENAV_SIMULATOR_H

#include <cstdint>
#include <functional>
#include <map>
#include <random>
#include <string>
#include <vector>
#include "pokenav/Grid.h"
#include "pokenav/Physics.h"
#include "pokenav/TileGrid.h"

namespace pokenav{


//  An NPC that tries a random step now and then (PhysicsModel's
//  npc_move_min_ms..npc_move_max_ms), staying within its patch. It blocks
//  the player.
struct Wanderer{
    std::string name;
    TilePos patch_min;
    TilePos patch_max;
};


struct WalkReport{
    //  Whether the walk read as stopped within its limit (a wall, an NPC):
    //  false is LIMIT.
    bool stopped = false;
    int tiles = 0;
};


class Simulator{
public:
    Simulator(const TileGrid& grid, const PhysicsModel& physics, TilePos start, Direction facing, uint64_t seed);

    //  Places a wanderer on a random standable tile of its patch.
    void add_wanderer(const Wanderer& wanderer);

    //  The actions. Each moves the clock on, and the wanderers with it.

    //  A short tap toward `direction`: turns if facing another way; facing
    //  it already, steps a tile if turn_when_facing_steps.
    void turn(Direction direction);
    //  `count` taps from standing, each a tile, sometimes two
    //  (tap_extra_tile_chance). Returns the tiles moved.
    int taps(Direction direction, int count);
    //  One timed one-tile hold, sometimes two tiles.
    int tile(Direction direction);
    //  One step that turns as it goes. Returns whether it moved.
    bool step(Direction direction);
    //  A hold of `ms`: ms / (ms per tile) tiles, until blocked.
    int hold(Direction direction, int64_t ms);
    //  turn(), then hold until stopped or `limit_tiles` tiles' time. The stop
    //  is seen `still_lag_mean_tiles` late on average (negative: the model's
    //  value); a stop seen after the limit reads as LIMIT.
    WalkReport walk_until_stopped(Direction direction, int limit_tiles, double still_lag_mean_tiles = -1);

    //  Whether the player could stand on `pos` now (no wanderer there).
    bool open(const TilePos& pos) const;

    TilePos position() const{ return m_pos; }
    Direction facing() const{ return m_facing; }
    int64_t clock_ms() const{ return m_clock; }
    //  Turn taps toward the way already faced that moved a tile.
    size_t turn_steps() const{ return m_turn_steps; }
    const std::vector<TilePos>& wanderer_positions() const{ return m_wanderer_pos; }
    const std::vector<std::string>& trace() const{ return m_trace; }
    const PhysicsModel& physics() const{ return m_physics; }
    const TileGrid& grid() const{ return m_grid; }

    bool chance(double p);
    void advance(int64_t ms);
    void log(const std::string& line);

private:
    bool move(Direction direction);
    int64_t ms_per_tile(Direction direction) const;

private:
    const TileGrid& m_grid;
    PhysicsModel m_physics;
    std::mt19937_64 m_rng;
    TilePos m_pos;
    Direction m_facing;
    int64_t m_clock = 0;
    size_t m_turn_steps = 0;
    std::vector<Wanderer> m_wanderers;
    std::vector<TilePos> m_wanderer_pos;
    std::vector<int64_t> m_wanderer_next_move;
    std::vector<std::string> m_trace;
};


//  Plays a robust plan's legs (plan_robust_route()): a leg to a wall is
//  walked until stopped, with room for a tile more than planned; an open leg
//  is a turn (only if facing another way) and `leg.tiles` taps. Returns "" if the player ends on one of the last
//  leg's `after` tiles, else what went wrong.
std::string play_planned_legs(Simulator& sim, const std::vector<PlannedLeg>& legs);


struct MonteCarloStats{
    size_t runs = 0;
    size_t successes = 0;
    double mean_ms = 0;
    int64_t max_ms = 0;
    double mean_success_ms = 0;
    size_t runs_with_turn_steps = 0;
    //  failure reason -> runs, and the first such run's seed and end tile.
    std::map<std::string, size_t> failures;
    std::map<std::string, std::string> failure_example;

    double success_rate() const{ return runs == 0 ? 0 : (double)successes / runs; }
    std::string to_string() const;
};

//  Runs `trial` on `runs` simulators made by `make` with seeds seed,
//  seed + 1, ... A trial returns "" for a success, else why it failed.
MonteCarloStats run_monte_carlo(
    const std::function<Simulator(uint64_t seed)>& make,
    const std::function<std::string(Simulator&)>& trial,
    size_t runs, uint64_t seed
);



}
#endif
