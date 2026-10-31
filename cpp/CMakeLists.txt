cmake_minimum_required(VERSION 3.10)
project(PokemonNavigation CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

add_library(pokenav
    src/Grid.cpp
    src/TileGrid.cpp
    src/MapSet.cpp
)
target_include_directories(pokenav PUBLIC include)

add_executable(pokenav_tests
    tests/main.cpp
    tests/LegPlanner_tests.cpp
    tests/TileGrid_tests.cpp
)
target_link_libraries(pokenav_tests PRIVATE pokenav)
target_compile_definitions(pokenav_tests PRIVATE
    POKENAV_GAMES_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../games")

enable_testing()
add_test(NAME pokenav_tests COMMAND pokenav_tests)
