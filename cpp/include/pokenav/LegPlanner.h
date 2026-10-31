/*  PokemonNavigation - Leg Planner
 *
 *  Ported from Arduino-Source (MIT): SerialPrograms/Source/Pokemon/Navigation/Pokemon_LegPlanner.h
 *
 *  Plans a walk as straight legs: hold one direction, then the next. The
 *  game decides what a single press does through its step model; the
 *  planner searches, joins steps into legs, and prefers legs that end
 *  against a wall, because the player stops there however long the button
 *  is held, while a leg that ends in the open depends on timing.
 *
 *  A step model is a class with:
 *
 *      using State = ...;      //  where the player is and what moves them:
 *                              //  comparable with ==
 *      using StateHash = ...;  //  a hash of State, e.g. std::hash<TilePos>
 *      std::optional<Step<State>> press(const State& state, Direction direction) const;
 *      bool held_at(const State& state, Direction direction) const;
 *
 *  press() is what pressing `direction` once does, or nothing if the player
 *  can't go that way (a wall, or something the plan must not do). held_at()
 *  is whether holding `direction` keeps the player on this tile: a wall, but
 *  not a person who may walk off or an edge to a map that isn't loaded.
 *
 */

#ifndef POKENAV_LEGPLANNER_H
#define POKENAV_LEGPLANNER_H

#include <algorithm>
#include <functional>
#include <limits>
#include <optional>
#include <queue>
#include <unordered_map>
#include <utility>
#include <vector>
#include "pokenav/Grid.h"

namespace pokenav{


//  What one press does.
template <typename State>
struct Step{
    State next;
    //  0 for a plain step. Anything else is a step of the game's own kind
    //  (e.g. starting to Surf), planned as a leg on its own.
    int action = 0;
    //  The step can't continue the leg before it, e.g. leaving the water,
    //  after which the player walks at another speed.
    bool starts_leg = false;
    //  No later step continues this leg: the game stops the player, e.g.
    //  at a warp.
    bool ends_leg = false;
    //  The step takes a warp: a door, a ladder, a cave entrance.
    bool warped = false;
    //  Which way the player faces afterwards. Usually the pressed direction;
    //  some warps turn the player.
    Direction facing = Direction::NORTH;
    //  Cost on top of LegCosts::per_tile: tall grass, a warp's fade, a dialog.
    int extra_cost = 0;
};


enum class LegKind{
    WALK,       //  hold `direction` for `tiles` steps
    ACTION,     //  one step of the game's own kind, `action`
    FACE,       //  turn to `direction` without moving
};

template <typename State>
struct Leg{
    LegKind kind = LegKind::WALK;
    int action = 0;
    Direction direction = Direction::NORTH;
    int tiles = 0;
    //  WALK: the last step takes a warp.
    bool warps = false;
    //  WALK: holding on keeps the player on the last tile, so the leg can be
    //  held for longer than it takes and walked again after an interruption.
    bool to_wall = false;
    Direction facing_after = Direction::NORTH;
    State start;
    State end;
};


struct LegCosts{
    int per_tile = 1;
    //  Extra for a step in a new direction.
    int per_turn = 2;
    //  Extra for ending a leg where the player could keep going: it has to
    //  be timed, and where an interruption leaves the player is a guess.
    int per_open_stop = 8;
};


//  The cheapest legs from `start` to a state where `at_goal` holds, facing
//  `goal_facing` if given, or nothing if there is none. `start_facing` is
//  the way the player faces at the start, if known.
template <typename Model>
std::optional<std::vector<Leg<typename Model::State>>> plan_legs(
    const Model& model,
    const typename Model::State& start, std::optional<Direction> start_facing,
    const std::function<bool(const typename Model::State&)>& at_goal,
    std::optional<Direction> goal_facing,
    const LegCosts& costs = LegCosts()
);



namespace LegPlannerInternal{

//  A search node: the player, the way they face (4: not known), and whether
//  they are in the middle of a leg that could go on.
template <typename State>
struct Node{
    State state;
    int facing = 4;
    bool moving = false;

    bool operator==(const Node& other) const{
        return state == other.state && facing == other.facing && moving == other.moving;
    }
};

template <typename State, typename StateHash>
struct NodeHash{
    size_t operator()(const Node<State>& node) const{
        return StateHash()(node.state) * 10 + node.facing * 2 + (node.moving ? 1 : 0);
    }
};

template <typename State>
struct Move{
    Node<State> from;
    Direction direction;
    Step<State> step;
};

template <typename Model, typename State>
int stop_cost(const Model& model, const Node<State>& node, const LegCosts& costs){
    if (!node.moving || model.held_at(node.state, (Direction)node.facing)){
        return 0;
    }
    return costs.per_open_stop;
}

template <typename Model, typename State>
std::vector<Leg<State>> join_legs(const Model& model, const State& start, const std::vector<Move<State>>& moves){
    std::vector<Leg<State>> legs;
    bool can_extend = false;
    State before = start;
    for (const Move<State>& move : moves){
        const Step<State>& step = move.step;
        const bool extends = can_extend && step.action == 0 && !step.starts_leg
            && legs.back().kind == LegKind::WALK && legs.back().direction == move.direction;
        if (extends){
            legs.back().tiles++;
        }else{
            Leg<State> leg;
            leg.kind = step.action == 0 ? LegKind::WALK : LegKind::ACTION;
            leg.action = step.action;
            leg.direction = move.direction;
            leg.tiles = 1;
            leg.start = before;
            legs.push_back(leg);
        }
        Leg<State>& leg = legs.back();
        leg.warps = step.warped;
        leg.to_wall = leg.kind == LegKind::WALK && !step.warped && model.held_at(step.next, move.direction);
        leg.facing_after = step.facing;
        leg.end = step.next;
        can_extend = step.action == 0 && !step.ends_leg;
        before = step.next;
    }
    return legs;
}

}



template <typename Model>
std::optional<std::vector<Leg<typename Model::State>>> plan_legs(
    const Model& model,
    const typename Model::State& start, std::optional<Direction> start_facing,
    const std::function<bool(const typename Model::State&)>& at_goal,
    std::optional<Direction> goal_facing,
    const LegCosts& costs
){
    using State = typename Model::State;
    using Node = LegPlannerInternal::Node<State>;
    using Move = LegPlannerInternal::Move<State>;
    using Hash = LegPlannerInternal::NodeHash<State, typename Model::StateHash>;
    const int INF = std::numeric_limits<int>::max();

    std::unordered_map<Node, int, Hash> distance;
    std::unordered_map<Node, Move, Hash> came_from;
    auto distance_of = [&](const Node& node){
        auto iter = distance.find(node);
        return iter == distance.end() ? INF : iter->second;
    };
    auto arrival_cost = [&](const Node& node){
        int cost = LegPlannerInternal::stop_cost(model, node, costs);
        if (goal_facing && node.facing != (int)*goal_facing){
            cost += costs.per_turn;
        }
        return cost;
    };

    const Node first{start, start_facing ? (int)*start_facing : 4, false};
    distance[first] = 0;

    //  Nodes are kept in a list and queued by index, so State needs no ordering.
    std::vector<Node> nodes{first};
    using Entry = std::pair<int, size_t>;
    std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> queue;
    queue.emplace(0, 0);

    std::optional<Node> best_end;
    int best_total = INF;
    while (!queue.empty()){
        const auto [cost, index] = queue.top();
        queue.pop();
        const Node current = nodes[index];
        if (cost != distance_of(current)){
            continue;
        }
        if (cost >= best_total){
            break;
        }
        if (at_goal(current.state)){
            const int total = cost + arrival_cost(current);
            if (total < best_total){
                best_total = total;
                best_end = current;
            }
            continue;
        }
        for (Direction direction : ALL_DIRECTIONS){
            std::optional<Step<State>> step = model.press(current.state, direction);
            if (!step){
                continue;
            }
            const bool continues = step->action == 0 && !step->ends_leg;
            const Node next{step->next, (int)step->facing, continues};
            int step_cost = costs.per_tile + step->extra_cost;
            if (current.facing != (int)direction){
                step_cost += costs.per_turn + LegPlannerInternal::stop_cost(model, current, costs);
            }
            if (cost + step_cost < distance_of(next)){
                distance[next] = cost + step_cost;
                came_from.insert_or_assign(next, Move{current, direction, *step});
                nodes.push_back(next);
                queue.emplace(cost + step_cost, nodes.size() - 1);
            }
        }
    }
    if (!best_end){
        return std::nullopt;
    }

    std::vector<Move> moves;
    for (Node node = *best_end; !(node == first); node = came_from.at(node).from){
        moves.push_back(came_from.at(node));
    }
    std::reverse(moves.begin(), moves.end());
    std::vector<Leg<State>> legs = LegPlannerInternal::join_legs(model, start, moves);
    if (goal_facing && best_end->facing != (int)*goal_facing){
        Leg<State> face;
        face.kind = LegKind::FACE;
        face.direction = *goal_facing;
        face.facing_after = *goal_facing;
        face.start = best_end->state;
        face.end = best_end->state;
        legs.push_back(face);
    }
    return legs;
}



}
#endif
