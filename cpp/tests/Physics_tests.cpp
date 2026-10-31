/*  PokemonNavigation - Physics model tests
 */

#include <string>
#include "pokenav/Error.h"
#include "pokenav/Physics.h"
#include "TestRunner.h"

namespace pokenav{
namespace test{


namespace{

Result test_defaults_are_guessed(){
    const PhysicsModel model;
    if (model.parameters().empty() || model.count(ParameterStatus::MEASURED) != 0){
        return "Every default should be a guess.";
    }
    if (model.get(physics::MS_PER_TILE_ACROSS) != 160){
        return "Default ms per tile across is " + std::to_string(model.get(physics::MS_PER_TILE_ACROSS)) + ".";
    }
    try{
        model.get("no_such_parameter");
        return "An unknown parameter was read.";
    }catch (Error&){}
    return true;
}

Result test_parse(){
    const PhysicsModel model = PhysicsModel::parse(
        "# comment\n"
        "\n"
        "tap_ms 600 measured  input timing, from the log\n"
        "tap_extra_tile_chance 0.1 guessed\n"
    );
    const Parameter& tap = model.parameter(physics::TAP_MS);
    if (tap.value != 600 || tap.status != ParameterStatus::MEASURED || tap.note != "input timing, from the log"){
        return "tap_ms parsed as " + std::to_string(tap.value) + " " + status_name(tap.status) + " '" + tap.note + "'.";
    }
    if (model.get(physics::TAP_EXTRA_TILE_CHANCE) != 0.1 || model.get(physics::TURN_MS) != 400){
        return "Overrides or defaults are wrong.";
    }
    for (const char* bad : {
        "tap_ms\n",
        "tap_ms 600\n",
        "tap_ms six measured\n",
        "tap_ms 600 known\n",
        "no_such_parameter 1 guessed\n",
    }){
        try{
            PhysicsModel::parse(bad);
            return std::string("Accepted: ") + bad;
        }catch (Error&){}
    }
    const PhysicsModel round = PhysicsModel::parse(model.to_text());
    if (round.to_text() != model.to_text()){
        return "to_text() does not read back the same.";
    }
    return true;
}

Result test_bdsp_file(){
    const PhysicsModel model = PhysicsModel::load(games_dir() + "/bdsp/physics.txt");
    log(model.to_text());
    for (const Parameter& p : model.parameters()){
        if (p.note == "default"){
            return "games/bdsp/physics.txt does not set " + p.name + ".";
        }
    }
    if (model.get(physics::TAP_MS) != 560 || model.parameter(physics::TAP_MS).status != ParameterStatus::MEASURED){
        return "BDSP tap_ms should be 560, measured.";
    }
    if (model.parameter(physics::TAP_EXTRA_TILE_CHANCE).status != ParameterStatus::GUESSED){
        return "BDSP tap_extra_tile_chance should be a guess.";
    }
    return true;
}

}


void add_tests_Physics(Database& database){
    database.add("Physics - defaults are guesses", test_defaults_are_guessed);
    database.add("Physics - parse", test_parse);
    database.add("Physics - BDSP parameter file", test_bdsp_file);
}



}
}
