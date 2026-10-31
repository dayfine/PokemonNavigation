/*  PokemonNavigation - Physics model
 *
 */

#include <cmath>
#include <fstream>
#include <sstream>
#include "pokenav/Error.h"
#include "pokenav/Physics.h"

namespace pokenav{


const char* status_name(ParameterStatus status){
    switch (status){
    case ParameterStatus::GUESSED:  return "guessed";
    case ParameterStatus::MEASURED: return "measured";
    }
    return "?";
}


PhysicsModel::PhysicsModel(){
    using namespace physics;
    auto add = [&](const char* name, double value, const char* unit, const char* note){
        m_parameters.push_back(Parameter{name, value, ParameterStatus::GUESSED, unit, note});
    };
    add(MS_PER_TILE_ACROSS,     160,    "ms",       "default");
    add(MS_PER_TILE_UP_DOWN,    240,    "ms",       "default");
    add(WALK_OVERHEAD_MS,       1050,   "ms",       "default");
    add(STILL_LAG_MEAN_TILES,   0,      "tiles",    "default: still is seen at once");
    add(TURN_MS,                400,    "ms",       "default");
    add(TURN_WHEN_FACING_STEPS, 1,      "bool",     "default");
    add(TAP_MS,                 560,    "ms",       "default");
    add(TAPS_SETTLE_MS,         800,    "ms",       "default");
    add(TAP_EXTRA_TILE_CHANCE,  0,      "chance",   "default: a tap is a tile");
    add(TILE_MS,                1000,   "ms",       "default");
    add(TILE_EXTRA_TILE_CHANCE, 0,      "chance",   "default: a hold is a tile");
    add(STEP_MS,                1200,   "ms",       "default");
    add(NPC_MOVE_MIN_MS,        2000,   "ms",       "default");
    add(NPC_MOVE_MAX_MS,        5000,   "ms",       "default");
}

PhysicsModel PhysicsModel::parse(const std::string& text){
    PhysicsModel model;
    std::istringstream lines(text);
    std::string line;
    size_t number = 0;
    while (std::getline(lines, line)){
        number++;
        std::istringstream words(line);
        std::string name;
        if (!(words >> name) || name[0] == '#'){
            continue;
        }
        std::string value_text, status_text;
        if (!(words >> value_text >> status_text)){
            throw Error("Physics line " + std::to_string(number) + ": expected 'name value measured|guessed note'.");
        }
        double value = 0;
        try{
            size_t used = 0;
            value = std::stod(value_text, &used);
            if (used != value_text.size()){
                throw std::invalid_argument(value_text);
            }
        }catch (std::exception&){
            throw Error("Physics line " + std::to_string(number) + ": bad value '" + value_text + "'.");
        }
        ParameterStatus status;
        if (status_text == "measured"){
            status = ParameterStatus::MEASURED;
        }else if (status_text == "guessed"){
            status = ParameterStatus::GUESSED;
        }else{
            throw Error("Physics line " + std::to_string(number) + ": status must be measured or guessed, got '" + status_text + "'.");
        }
        std::string note;
        std::getline(words, note);
        const size_t start = note.find_first_not_of(" \t");
        note = start == std::string::npos ? "" : note.substr(start);
        if (model.find(name) == nullptr){
            throw Error("Physics line " + std::to_string(number) + ": unknown parameter '" + name + "'.");
        }
        model.set(name, value, status, note);
    }
    return model;
}

PhysicsModel PhysicsModel::load(const std::string& path){
    std::ifstream file(path);
    if (!file){
        throw Error("Cannot read physics file: " + path);
    }
    std::ostringstream text;
    text << file.rdbuf();
    return parse(text.str());
}

Parameter* PhysicsModel::find(const std::string& name){
    for (Parameter& p : m_parameters){
        if (p.name == name){
            return &p;
        }
    }
    return nullptr;
}
const Parameter* PhysicsModel::find(const std::string& name) const{
    for (const Parameter& p : m_parameters){
        if (p.name == name){
            return &p;
        }
    }
    return nullptr;
}

const Parameter& PhysicsModel::parameter(const std::string& name) const{
    const Parameter* p = find(name);
    if (p == nullptr){
        throw Error("Unknown physics parameter: " + name);
    }
    return *p;
}

double PhysicsModel::get(const std::string& name) const{
    return parameter(name).value;
}

void PhysicsModel::set(const std::string& name, double value, ParameterStatus status, const std::string& note){
    Parameter* p = find(name);
    if (p == nullptr){
        throw Error("Unknown physics parameter: " + name);
    }
    p->value = value;
    p->status = status;
    p->note = note;
}

size_t PhysicsModel::count(ParameterStatus status) const{
    size_t n = 0;
    for (const Parameter& p : m_parameters){
        n += p.status == status ? 1 : 0;
    }
    return n;
}

std::string PhysicsModel::to_text() const{
    std::ostringstream out;
    for (const Parameter& p : m_parameters){
        out << p.name << " " << p.value << " " << status_name(p.status);
        if (!p.note.empty()){
            out << " " << p.note;
        }
        out << "\n";
    }
    return out.str();
}



}
