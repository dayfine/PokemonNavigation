/*  PokemonNavigation - test runner
 *
 *  pokenav_tests [-v] [filter]: runs every test whose name contains filter.
 */

#include <exception>
#include <iostream>
#include <string>
#include "TestRunner.h"

namespace pokenav{
namespace test{

namespace{
bool g_verbose = false;
}

void log(const std::string& line){
    if (g_verbose){
        std::cout << "    " << line << "\n";
    }
}

std::string games_dir(){
    return POKENAV_GAMES_DIR;
}

}
}


int main(int argc, char** argv){
    using namespace pokenav::test;
    std::string filter;
    for (int i = 1; i < argc; i++){
        const std::string arg = argv[i];
        if (arg == "-v"){
            g_verbose = true;
        }else{
            filter = arg;
        }
    }
    Database database;
    add_tests_LegPlanner(database);
    add_tests_TileGrid(database);
    add_tests_Physics(database);
    add_tests_Simulator(database);

    size_t run = 0;
    size_t failed = 0;
    for (const Test& test : database.tests()){
        if (!filter.empty() && test.name.find(filter) == std::string::npos){
            continue;
        }
        run++;
        Result result(true);
        try{
            result = test.body();
        }catch (std::exception& e){
            result = Result(std::string("threw: ") + e.what());
        }
        if (result.ok){
            std::cout << "PASS " << test.name << "\n";
        }else{
            failed++;
            std::cout << "FAIL " << test.name << "\n    " << result.message << "\n";
        }
    }
    std::cout << (run - failed) << " / " << run << " passed\n";
    return failed == 0 && run > 0 ? 0 : 1;
}
