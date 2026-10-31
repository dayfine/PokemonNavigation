/*  PokemonNavigation - Movement simulator
 *
 *  Ported from Arduino-Source (MIT), branch bdsp/grid-sim:
 *  SerialPrograms/Source/PokemonBDSP/Programs/AutoStory/PokemonBDSP_AutoStory_Sim.cpp
 */

#include <algorithm>
#include <cmath>
#include <optional>
#include <sstream>
#include "pokenav/Error.h"
#include "pokenav/Simulator.h"

namespace pokenav{


Simulator::Simulator(const TileGrid& grid, const PhysicsModel& physics, TilePos start, Direction facing, uint64_t seed)
    : m_grid(grid)
    , m_physics(physics)
    , m_rng(seed)
    , m_pos(start)
    , m_facing(facing)
{
    if (!grid.standable(start)){
        throw Error("Simulator start is not standable: " + to_string(start));
    }
}

void Simulator::add_wanderer(const Wanderer& wanderer){
    std::vector<TilePos> patch;
    for (int y = wanderer.patch_min.y; y <= wanderer.patch_max.y; y++){
        for (int x = wanderer.patch_min.x; x <= wanderer.patch_max.x; x++){
            if (m_grid.standable({x, y}) && !(TilePos{x, y} == m_pos)){
                patch.push_back({x, y});
            }
        }
    }
    if (patch.empty()){
        throw Error("Wanderer " + wanderer.name + " has no tile to stand on.");
    }
    m_wanderers.push_back(wanderer);
    m_wanderer_pos.push_back(patch[std::uniform_int_distribution<size_t>(0, patch.size() - 1)(m_rng)]);
    const int64_t max_ms = (int64_t)m_physics.get(physics::NPC_MOVE_MAX_MS);
    m_wanderer_next_move.push_back(m_clock + std::uniform_int_distribution<int64_t>(0, max_ms)(m_rng));
}

bool Simulator::chance(double p){
    return std::uniform_real_distribution<double>(0, 1)(m_rng) < p;
}

void Simulator::advance(int64_t ms){
    m_clock += ms;
    const int64_t min_ms = (int64_t)m_physics.get(physics::NPC_MOVE_MIN_MS);
    const int64_t max_ms = (int64_t)m_physics.get(physics::NPC_MOVE_MAX_MS);
    for (size_t i = 0; i < m_wanderers.size(); i++){
        const Wanderer& w = m_wanderers[i];
        while (m_wanderer_next_move[i] <= m_clock){
            const Direction direction = ALL_DIRECTIONS[std::uniform_int_distribution<int>(0, 3)(m_rng)];
            const TilePos next = m_wanderer_pos[i].next(direction);
            const bool in_patch = next.x >= w.patch_min.x && next.x <= w.patch_max.x &&
                next.y >= w.patch_min.y && next.y <= w.patch_max.y;
            if (in_patch && open(next) && next != m_pos){
                m_wanderer_pos[i] = next;
            }
            m_wanderer_next_move[i] += std::uniform_int_distribution<int64_t>(min_ms, std::max(min_ms, max_ms))(m_rng);
        }
    }
}

bool Simulator::open(const TilePos& pos) const{
    return m_grid.standable(pos) &&
        std::find(m_wanderer_pos.begin(), m_wanderer_pos.end(), pos) == m_wanderer_pos.end();
}

bool Simulator::move(Direction direction){
    m_facing = direction;
    const std::optional<TilePos> next = m_grid.step(m_pos, direction);
    if (!next || !open(*next)){
        return false;
    }
    m_pos = *next;
    return true;
}

int64_t Simulator::ms_per_tile(Direction direction) const{
    return (int64_t)m_physics.get(direction == Direction::EAST || direction == Direction::WEST
        ? physics::MS_PER_TILE_ACROSS
        : physics::MS_PER_TILE_UP_DOWN);
}

void Simulator::log(const std::string& line){
    m_trace.push_back(
        std::to_string(m_clock) + " ms " + to_string(m_pos) + " " +
        direction_name(m_facing) + ": " + line
    );
}

void Simulator::turn(Direction direction){
    advance((int64_t)m_physics.get(physics::TURN_MS));
    if (m_facing != direction){
        m_facing = direction;
        return;
    }
    if (m_physics.get(physics::TURN_WHEN_FACING_STEPS) != 0 && move(direction)){
        m_turn_steps++;
        log(std::string("turn ") + direction_name(direction) + " was a step");
    }
}

int Simulator::taps(Direction direction, int count){
    const TilePos start = m_pos;
    const double extra = m_physics.get(physics::TAP_EXTRA_TILE_CHANCE);
    for (int i = 0; i < count; i++){
        advance((int64_t)m_physics.get(physics::TAP_MS));
        if (move(direction) && chance(extra)){
            move(direction);
        }
    }
    advance((int64_t)m_physics.get(physics::TAPS_SETTLE_MS));
    log(std::to_string(count) + " taps " + direction_name(direction));
    return std::abs(m_pos.x - start.x) + std::abs(m_pos.y - start.y);
}

int Simulator::tile(Direction direction){
    const TilePos start = m_pos;
    advance((int64_t)m_physics.get(physics::TILE_MS));
    if (move(direction) && chance(m_physics.get(physics::TILE_EXTRA_TILE_CHANCE))){
        move(direction);
    }
    log(std::string("tile ") + direction_name(direction));
    return std::abs(m_pos.x - start.x) + std::abs(m_pos.y - start.y);
}

bool Simulator::step(Direction direction){
    advance((int64_t)m_physics.get(physics::STEP_MS));
    const bool moved = move(direction);
    log(std::string("step ") + direction_name(direction) + (moved ? "" : ": blocked"));
    return moved;
}

int Simulator::hold(Direction direction, int64_t ms){
    const TilePos start = m_pos;
    const int64_t tiles = ms / ms_per_tile(direction);
    advance(ms + (int64_t)m_physics.get(physics::TURN_MS));
    for (int64_t i = 0; i < tiles; i++){
        move(direction);
    }
    log(std::string("hold ") + direction_name(direction) + " " + std::to_string(ms) + " ms");
    return std::abs(m_pos.x - start.x) + std::abs(m_pos.y - start.y);
}

WalkReport Simulator::walk_until_stopped(Direction direction, int limit_tiles, double still_lag_mean_tiles){
    if (still_lag_mean_tiles < 0){
        still_lag_mean_tiles = m_physics.get(physics::STILL_LAG_MEAN_TILES);
    }
    turn(direction);
    advance((int64_t)m_physics.get(physics::WALK_OVERHEAD_MS));
    WalkReport report;
    while (report.tiles < limit_tiles){
        advance(ms_per_tile(direction));
        const TilePos before = m_pos;
        if (!move(direction)){
            report.stopped = true;
            break;
        }
        report.tiles += std::abs(m_pos.x - before.x) + std::abs(m_pos.y - before.y);
    }
    if (!report.stopped){
        //  Still walking at the limit: stopped only if the next tile is shut.
        const std::optional<TilePos> next = m_grid.step(m_pos, direction);
        report.stopped = !next || !open(*next);
    }
    if (report.stopped && still_lag_mean_tiles > 0){
        const double lag = std::exponential_distribution<double>(1.0 / still_lag_mean_tiles)(m_rng);
        const double seen = std::min<double>(report.tiles + lag, limit_tiles);
        advance((int64_t)((seen - report.tiles) * (double)ms_per_tile(direction)));
        if (report.tiles + lag > limit_tiles){
            report.stopped = false;
        }
    }
    log(std::string("walk ") + direction_name(direction) + ": " +
        (report.stopped ? "stopped" : "limit") + " after " + std::to_string(report.tiles));
    return report;
}


std::string play_planned_legs(Simulator& sim, const std::vector<PlannedLeg>& legs){
    for (size_t i = 0; i < legs.size(); i++){
        const PlannedLeg& planned = legs[i];
        const TileLeg& leg = planned.leg;
        if (leg.ends_at_wall){
            const WalkReport walked = sim.walk_until_stopped(leg.direction, (int)leg.tiles + 1);
            if (!walked.stopped){
                return "leg " + std::to_string(i + 1) + " " + to_string(leg) + ": not stopped";
            }
        }else{
            //  Turn only when facing another way: a turn tap toward the way
            //  already faced may step (turn_when_facing_steps).
            if (sim.facing() != leg.direction){
                sim.turn(leg.direction);
            }
            sim.taps(leg.direction, (int)leg.tiles);
        }
        if (std::find(planned.after.begin(), planned.after.end(), sim.position()) == planned.after.end()){
            return "leg " + std::to_string(i + 1) + " " + to_string(leg) + ": off the plan";
        }
    }
    return "";
}


std::string MonteCarloStats::to_string() const{
    std::ostringstream out;
    out.setf(std::ios::fixed);
    out.precision(1);
    out << successes << " / " << runs << " succeeded (" << 100 * success_rate() << "%)";
    out << "; time mean " << mean_ms / 1000 << " s, max " << (double)max_ms / 1000 <<
        " s, mean when it succeeded " << mean_success_ms / 1000 << " s";
    if (runs_with_turn_steps > 0){
        out << "; " << runs_with_turn_steps << " runs had a turn that stepped";
    }
    std::vector<std::pair<std::string, size_t>> sorted(failures.begin(), failures.end());
    std::sort(sorted.begin(), sorted.end(), [](const std::pair<std::string, size_t>& a, const std::pair<std::string, size_t>& b){
        return a.second > b.second;
    });
    for (const auto& item : sorted){
        out << "\n    " << item.second << " x " << item.first << "  (e.g. " << failure_example.at(item.first) << ")";
    }
    return out.str();
}

MonteCarloStats run_monte_carlo(
    const std::function<Simulator(uint64_t seed)>& make,
    const std::function<std::string(Simulator&)>& trial,
    size_t runs, uint64_t seed
){
    MonteCarloStats stats;
    double total_ms = 0;
    double success_ms = 0;
    for (size_t i = 0; i < runs; i++){
        Simulator sim = make(seed + i);
        const std::string failure = trial(sim);
        stats.runs++;
        total_ms += (double)sim.clock_ms();
        stats.max_ms = std::max(stats.max_ms, sim.clock_ms());
        if (sim.turn_steps() > 0){
            stats.runs_with_turn_steps++;
        }
        if (failure.empty()){
            stats.successes++;
            success_ms += (double)sim.clock_ms();
            continue;
        }
        const std::string reason = failure + " @ " + pokenav::to_string(sim.position());
        if (stats.failures[reason]++ == 0){
            stats.failure_example[reason] = "seed " + std::to_string(seed + i) + ", facing " +
                direction_name(sim.facing());
        }
    }
    stats.mean_ms = runs == 0 ? 0 : total_ms / runs;
    stats.mean_success_ms = stats.successes == 0 ? 0 : success_ms / stats.successes;
    return stats;
}



}
