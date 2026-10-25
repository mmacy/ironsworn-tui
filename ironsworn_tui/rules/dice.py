"""Dice, challenge dice, and the three hit results."""

import random
from enum import IntEnum

from ironsworn_tui.rules.errors import RulesError

type ChallengeDice = tuple[int, int]


class Hit(IntEnum):
    """The result of an action or progress roll, ordered from worst to best."""

    MISS = 0
    WEAK = 1
    STRONG = 2

    @property
    def label(self) -> str:
        """The result as the rulebook names it, such as "strong hit"."""
        return {Hit.MISS: "miss", Hit.WEAK: "weak hit", Hit.STRONG: "strong hit"}[self]


def check_die(value: int, sides: int, name: str) -> None:
    """Raise if a die result is outside `1..sides`.

    Raises:
        RulesError: If `value` is less than 1 or greater than `sides`.
    """
    if not 1 <= value <= sides:
        raise RulesError(f"{name} must be 1 to {sides}, got {value}")


def check_challenge_dice(challenge_dice: ChallengeDice) -> None:
    """Raise if either challenge die is outside `1..10`.

    Raises:
        RulesError: If a die is outside `1..10`.
    """
    for die in challenge_dice:
        check_die(die, 10, "a challenge die")


def roll_challenge_dice(rng: random.Random) -> ChallengeDice:
    """Roll the two d10 challenge dice."""
    return (rng.randint(1, 10), rng.randint(1, 10))


def hit_for(score: int, challenge_dice: ChallengeDice) -> Hit:
    """Compare a score with the challenge dice.

    The score must be greater than a die to beat it. Beating both is a strong hit, beating one is
    a weak hit, and beating neither is a miss.
    """
    beaten = sum(score > die for die in challenge_dice)
    return Hit(beaten)
