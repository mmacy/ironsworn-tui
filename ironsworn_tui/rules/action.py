"""Action rolls and burning momentum."""

import dataclasses
import random
from dataclasses import dataclass

from ironsworn_tui.rules.dice import (
    ChallengeDice,
    Hit,
    check_challenge_dice,
    check_die,
    hit_for,
    roll_challenge_dice,
)
from ironsworn_tui.rules.errors import RulesError
from ironsworn_tui.rules.momentum import check_momentum

ACTION_SCORE_MAX = 10


@dataclass(frozen=True)
class ActionRoll:
    """An action roll: a d6 plus a value and adds, against two d10 challenge dice.

    Attributes:
        action_die: The d6 as rolled, even when negative momentum cancelled it.
        challenge_dice: The two d10s.
        value: The stat or meter rolled with.
        adds: The bonus added to the roll.
        momentum: The character's momentum at the time of the roll.
        action_die_cancelled: True when momentum was negative and equal to the action die, so the
            die counted as 0.
        raw_score: The die plus value plus adds, before the cap of 10.
        score: The action score before any burn.
        hit: The result.
        burned: True when the player burned momentum on this roll.
    """

    action_die: int
    challenge_dice: ChallengeDice
    value: int
    adds: int
    momentum: int
    action_die_cancelled: bool
    raw_score: int
    score: int
    hit: Hit
    burned: bool = False

    @property
    def capped(self) -> bool:
        """True when the raw score was over 10 and the cap applied."""
        return self.raw_score > ACTION_SCORE_MAX

    @property
    def match(self) -> bool:
        """True when the challenge dice show the same number."""
        return self.challenge_dice[0] == self.challenge_dice[1]

    @property
    def burn_available(self) -> bool:
        """True when burning momentum would give a better result than the roll has."""
        if self.burned or self.momentum <= 0:
            return False
        return _burned_hit(self.score, self.momentum, self.challenge_dice) > self.hit


def _burned_hit(score: int, momentum: int, challenge_dice: ChallengeDice) -> Hit:
    """The result after burning: each die below the momentum is cancelled, and the rest stand."""
    return hit_for(max(score, min(momentum, ACTION_SCORE_MAX)), challenge_dice)


def evaluate_action(
    value: int,
    adds: int,
    momentum: int,
    action_die: int,
    challenge_dice: ChallengeDice,
) -> ActionRoll:
    """Work out an action roll from dice that are already rolled.

    When momentum is negative and equal to the action die, the die counts as 0. The action score
    is the die plus `value` plus `adds`, up to 10.

    Args:
        value: The stat or meter rolled with.
        adds: The bonus added to the roll.
        momentum: The character's momentum, -6 to +10.
        action_die: The d6 result.
        challenge_dice: The two d10 results.

    Returns:
        The roll and its result.

    Raises:
        RulesError: If a die or the momentum is out of range.
    """
    check_die(action_die, 6, "the action die")
    check_challenge_dice(challenge_dice)
    check_momentum(momentum)
    cancelled = momentum < 0 and action_die == -momentum
    raw_score = (0 if cancelled else action_die) + value + adds
    score = min(raw_score, ACTION_SCORE_MAX)
    return ActionRoll(
        action_die=action_die,
        challenge_dice=challenge_dice,
        value=value,
        adds=adds,
        momentum=momentum,
        action_die_cancelled=cancelled,
        raw_score=raw_score,
        score=score,
        hit=hit_for(score, challenge_dice),
    )


def roll_action(value: int, adds: int, momentum: int, rng: random.Random) -> ActionRoll:
    """Roll the action die and challenge dice, then work out the result.

    See [`evaluate_action`][ironsworn_tui.rules.action.evaluate_action] for the rules.

    Args:
        value: The stat or meter rolled with.
        adds: The bonus added to the roll.
        momentum: The character's momentum, -6 to +10.
        rng: The source of the dice.

    Returns:
        The roll and its result.
    """
    action_die = rng.randint(1, 6)
    return evaluate_action(value, adds, momentum, action_die, roll_challenge_dice(rng))


def burn_momentum(roll: ActionRoll) -> ActionRoll:
    """Burn momentum on a roll, against the same dice.

    Each challenge die lower than the momentum is cancelled, and any other die stands against the
    action score, so burning never makes the result worse. The caller resets the character's
    momentum afterward, to the reset value from
    [`momentum_bounds`][ironsworn_tui.rules.momentum.momentum_bounds].

    Args:
        roll: The roll to burn momentum on.

    Returns:
        The roll with `burned` set and the new result.

    Raises:
        RulesError: If momentum isn't positive or the roll was already burned.
    """
    if roll.burned:
        raise RulesError("momentum was already burned on this roll")
    if roll.momentum <= 0:
        raise RulesError(f"momentum must be positive to burn, got {roll.momentum}")
    return dataclasses.replace(
        roll, hit=_burned_hit(roll.score, roll.momentum, roll.challenge_dice), burned=True
    )
