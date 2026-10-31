"""Leg execution: what a bot presses for each planned leg.

`routing.belief` plans legs by how they end (a wall, a ledge landing, an
open stop, a door). This module names how each is walked, and turns a plan
into a plain list a bot can run:

    bot_legs(plan)
    # [("door", "S"), ("dpad", "W", 20), ("door", "N")]

A mode change shows as ("mount",) or ("dismount",) before the first leg in
the new mode. When the planner picks each kind: docs/LEG_KINDS.md.
"""

import enum
from typing import Iterable, List, Tuple

from pokenav.physics.model import Mode


class Execution(enum.Enum):
    """How a leg is walked."""

    CLIP = "clip"          #   stick held until stopped against a wall: exact on that axis
    RUN = "run"            #   the same with B held: faster, for legs that end at a wall
    LEDGE = "ledge"        #   stick held until the first ledge hop lands: pins the landing row
    DPAD = "dpad"          #   N D-pad taps, each checked to have moved a tile
    STICK_HOLD = "stick"   #   a stick hold timed for N tiles: spreads by the error model
    DOOR = "door"          #   a turn tap if needed, then a hold through the door ahead; the fade proves it


#   Kinds whose length is counted, so the bot is told how many tiles.
COUNTED = frozenset({Execution.DPAD, Execution.STICK_HOLD})

#   Kinds started with a tap: a first tap toward a new direction only turns.
TAPPED = frozenset({Execution.DPAD, Execution.DOOR})

BotLeg = Tuple


def bot_leg(leg) -> BotLeg:
    """One planned leg as (kind, direction letter[, tiles])."""
    letter = leg.direction.name[0]
    if leg.execution in COUNTED:
        return (leg.execution.value, letter, leg.tiles)
    return (leg.execution.value, letter)


def bot_legs(legs: Iterable) -> List[BotLeg]:
    """Planned legs (`routing.belief.PlannedLeg`) as a bot's list, starting
    on foot."""
    out: List[BotLeg] = []
    mode = Mode.FOOT
    for leg in legs:
        if leg.mode is not mode:
            out.append(("mount",) if leg.mode is Mode.BIKE else ("dismount",))
            mode = leg.mode
        out.append(bot_leg(leg))
    return out
