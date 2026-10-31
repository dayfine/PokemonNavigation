/*  PokemonNavigation - Physics model
 *
 *  How the player moves for each input, as named numbers: each marked
 *  measured (a measurement in measurements/ backs it) or guessed. A game's
 *  values live in games/<game>/physics.txt and override the defaults here.
 *
 *  File format, one parameter per line:
 *
 *      # comment
 *      name  value  measured|guessed  note to the end of the line
 *
 *  The movement model is the one of the Arduino-Source BDSP simulator
 *  (bdsp/grid-sim, PokemonBDSP_AutoStory_Sim.h: SimModel), made data.
 */

#ifndef POKENAV_PHYSICS_H
#define POKENAV_PHYSICS_H

#include <string>
#include <vector>

namespace pokenav{


enum class ParameterStatus{
    GUESSED,
    MEASURED,
};
const char* status_name(ParameterStatus status);


struct Parameter{
    std::string name;
    double value = 0;
    ParameterStatus status = ParameterStatus::GUESSED;
    std::string unit;
    std::string note;
};


class PhysicsModel{
public:
    //  Every parameter the simulator reads, with a generic default (guessed).
    PhysicsModel();

    //  The defaults, overridden by `text` (the file format above). Throws
    //  Error for an unknown name, a bad value or status, or a malformed line.
    static PhysicsModel parse(const std::string& text);
    static PhysicsModel load(const std::string& path);

    //  Throws Error for an unknown name.
    double get(const std::string& name) const;
    const Parameter& parameter(const std::string& name) const;
    void set(const std::string& name, double value, ParameterStatus status, const std::string& note = "");

    const std::vector<Parameter>& parameters() const{ return m_parameters; }
    size_t count(ParameterStatus status) const;

    //  The file format, every parameter.
    std::string to_text() const;

private:
    Parameter* find(const std::string& name);
    const Parameter* find(const std::string& name) const;

    std::vector<Parameter> m_parameters;
};


//  Parameter names.
namespace physics{
    //  Time per tile walking, across (east/west) and up/down (north/south).
    constexpr const char* MS_PER_TILE_ACROSS        = "ms_per_tile_across";
    constexpr const char* MS_PER_TILE_UP_DOWN       = "ms_per_tile_up_down";
    //  A walk until stopped: start delay plus the wait to read "still".
    constexpr const char* WALK_OVERHEAD_MS          = "walk_overhead_ms";
    //  How late "still" is seen, in tiles' time, on average (exponential).
    //  0 where nothing animates nearby; a place can set its own.
    constexpr const char* STILL_LAG_MEAN_TILES      = "still_lag_mean_tiles";
    //  A turn tap: its length (hold and wait), and whether a tap toward the
    //  way already faced steps a tile (1) or does nothing (0).
    constexpr const char* TURN_MS                   = "turn_ms";
    constexpr const char* TURN_WHEN_FACING_STEPS    = "turn_when_facing_steps";
    //  Taps from standing: one tap's period (hold plus gap), the settle wait
    //  after the last, and the chance one tap moves two tiles instead of one.
    constexpr const char* TAP_MS                    = "tap_ms";
    constexpr const char* TAPS_SETTLE_MS            = "taps_settle_ms";
    constexpr const char* TAP_EXTRA_TILE_CHANCE     = "tap_extra_tile_chance";
    //  A single one-tile hold (tile()): its time and its chance to go two.
    constexpr const char* TILE_MS                   = "tile_ms";
    constexpr const char* TILE_EXTRA_TILE_CHANCE    = "tile_extra_tile_chance";
    //  A single step that turns as it goes (step()).
    constexpr const char* STEP_MS                   = "step_ms";
    //  NPCs that wander: time between their step attempts, uniform.
    constexpr const char* NPC_MOVE_MIN_MS           = "npc_move_min_ms";
    constexpr const char* NPC_MOVE_MAX_MS           = "npc_move_max_ms";
}



}
#endif
