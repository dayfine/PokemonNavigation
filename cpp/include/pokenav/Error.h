/*  PokemonNavigation - Errors
 *
 *  The library throws pokenav::Error for bad input (a malformed grid, a
 *  route end that is not standable, an unknown parameter). Bots wrap it in
 *  their own error type where they call the library.
 */

#ifndef POKENAV_ERROR_H
#define POKENAV_ERROR_H

#include <functional>
#include <stdexcept>
#include <string>

namespace pokenav{


class Error : public std::runtime_error{
public:
    explicit Error(const std::string& message)
        : std::runtime_error(message)
    {}
};


//  Where the library writes what it is doing, if anywhere: a line at a time.
//  Bots pass their own logger; the default drops the lines.
using Logger = std::function<void(const std::string& line)>;



}
#endif
