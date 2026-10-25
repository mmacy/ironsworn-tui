"""Endure Harm and Endure Stress."""

import dataclasses
import random
from dataclasses import dataclass
from typing import Literal

from ironsworn_tui.rules.action import ActionRoll, burn_momentum, evaluate_action
from ironsworn_tui.rules.dice import ChallengeDice, Hit, roll_challenge_dice
from ironsworn_tui.rules.errors import RulesError
from ironsworn_tui.rules.momentum import adjust_momentum, check_momentum

ENDURE_HARM_TABLE = "classic/suffer/endure_harm/endure_harm"
ENDURE_STRESS_TABLE = "classic/suffer/endure_stress/endure_stress"
METER_MAX = 5
STAT_MAX = 5

type Meter = Literal["health", "spirit"]
type EnduranceStat = Literal["health", "iron", "spirit", "heart"]


@dataclass(frozen=True)
class Endurance:
    """An Endure Harm or Endure Stress move: the damage, then the roll.

    The damage comes off the meter first. When the meter reaches 0, the rest comes off momentum,
    down to -6. The roll then uses the higher of the meter after damage and the stat (iron for
    harm, heart for stress).

    Attributes:
        meter: The meter that took the damage.
        meter_after: The meter's value after the damage.
        momentum_after: Momentum after any damage that spilled over.
        spill: The damage the meter couldn't absorb.
        setback: The part of the spill that would have taken momentum below -6. See
            [`adjust_momentum`][ironsworn_tui.rules.momentum.adjust_momentum].
        stat: What the roll used: the meter, or the stat when it was higher.
        roll: The action roll.
        fate_table_id: The oracle table for a miss at 0. See
            [`fate_triggered`][ironsworn_tui.rules.suffer.Endurance.fate_triggered].
    """

    meter: Meter
    meter_after: int
    momentum_after: int
    spill: int
    setback: int
    stat: EnduranceStat
    roll: ActionRoll
    fate_table_id: str

    @property
    def fate_triggered(self) -> bool:
        """True on a miss with the meter at 0.

        The move then says to mark a debility (wounded or maimed for harm, shaken or corrupted
        for stress) if one is unmarked, or roll on the move's table. The rules don't track
        debilities, so the caller decides whether the player has that choice.
        """
        return self.roll.hit is Hit.MISS and self.meter_after == 0

    def burn(self) -> Endurance:
        """Burn momentum on the roll.

        Returns:
            The same move with the burned roll.

        Raises:
            RulesError: If momentum isn't positive or was already burned.
        """
        return dataclasses.replace(self, roll=burn_momentum(self.roll))


def _check_range(value: int, top: int, name: str) -> None:
    if not 0 <= value <= top:
        raise RulesError(f"{name} must be 0 to {top}, got {value}")


def _endure(
    meter: Meter,
    meter_value: int,
    stat: EnduranceStat,
    stat_value: int,
    amount: int,
    momentum: int,
    action_die: int,
    challenge_dice: ChallengeDice,
    fate_table_id: str,
) -> Endurance:
    _check_range(meter_value, METER_MAX, meter)
    _check_range(stat_value, STAT_MAX, stat)
    if amount < 0:
        raise RulesError(f"the amount suffered must be non-negative, got {amount}")
    check_momentum(momentum)
    absorbed = min(meter_value, amount)
    meter_after = meter_value - absorbed
    spill = amount - absorbed
    change = adjust_momentum(momentum, -spill)
    use_meter = meter_after >= stat_value
    roll = evaluate_action(
        value=meter_after if use_meter else stat_value,
        adds=0,
        momentum=change.momentum,
        action_die=action_die,
        challenge_dice=challenge_dice,
    )
    return Endurance(
        meter=meter,
        meter_after=meter_after,
        momentum_after=change.momentum,
        spill=spill,
        setback=change.setback,
        stat=meter if use_meter else stat,
        roll=roll,
        fate_table_id=fate_table_id,
    )


def evaluate_endure_harm(
    health: int,
    iron: int,
    harm: int,
    momentum: int,
    action_die: int,
    challenge_dice: ChallengeDice,
) -> Endurance:
    """Work out Endure Harm from dice that are already rolled.

    Args:
        health: Health before the harm, 0 to 5.
        iron: The iron stat, 0 to 5.
        harm: The harm suffered.
        momentum: Momentum before the harm.
        action_die: The d6 result.
        challenge_dice: The two d10 results.

    Returns:
        The damage and the roll.

    Raises:
        RulesError: If a value or die is out of range.
    """
    return _endure(
        "health",
        health,
        "iron",
        iron,
        harm,
        momentum,
        action_die,
        challenge_dice,
        ENDURE_HARM_TABLE,
    )


def roll_endure_harm(
    health: int, iron: int, harm: int, momentum: int, rng: random.Random
) -> Endurance:
    """Roll the dice for Endure Harm and work out the result."""
    action_die = rng.randint(1, 6)
    return evaluate_endure_harm(health, iron, harm, momentum, action_die, roll_challenge_dice(rng))


def evaluate_endure_stress(
    spirit: int,
    heart: int,
    stress: int,
    momentum: int,
    action_die: int,
    challenge_dice: ChallengeDice,
) -> Endurance:
    """Work out Endure Stress from dice that are already rolled.

    Args:
        spirit: Spirit before the stress, 0 to 5.
        heart: The heart stat, 0 to 5.
        stress: The stress suffered.
        momentum: Momentum before the stress.
        action_die: The d6 result.
        challenge_dice: The two d10 results.

    Returns:
        The damage and the roll.

    Raises:
        RulesError: If a value or die is out of range.
    """
    return _endure(
        "spirit",
        spirit,
        "heart",
        heart,
        stress,
        momentum,
        action_die,
        challenge_dice,
        ENDURE_STRESS_TABLE,
    )


def roll_endure_stress(
    spirit: int, heart: int, stress: int, momentum: int, rng: random.Random
) -> Endurance:
    """Roll the dice for Endure Stress and work out the result."""
    action_die = rng.randint(1, 6)
    return evaluate_endure_stress(
        spirit, heart, stress, momentum, action_die, roll_challenge_dice(rng)
    )
