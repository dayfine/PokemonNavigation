/*  PokemonNavigation - a small test runner
 *
 *  Stands in for Arduino-Source's UnitTest base: a test is a function that
 *  returns true, or a message saying what went wrong.
 */

#ifndef POKENAV_TESTS_TESTRUNNER_H
#define POKENAV_TESTS_TESTRUNNER_H

#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace pokenav{
namespace test{


struct Result{
    bool ok = true;
    std::string message;

    Result(bool passed) : ok(passed), message(passed ? "" : "failed") {}
    Result(const char* failure) : ok(false), message(failure) {}
    Result(std::string failure) : ok(false), message(std::move(failure)) {}
};

struct Test{
    std::string name;
    std::function<Result()> body;
};

class Database{
public:
    void add(std::string name, std::function<Result()> body){
        m_tests.push_back(Test{std::move(name), std::move(body)});
    }
    const std::vector<Test>& tests() const{ return m_tests; }

private:
    std::vector<Test> m_tests;
};

//  Lines a test wants to show (plans, statistics); printed with -v.
void log(const std::string& line);

//  games/ in the source tree.
std::string games_dir();

void add_tests_LegPlanner(Database& database);
void add_tests_TileGrid(Database& database);



}
}
#endif
