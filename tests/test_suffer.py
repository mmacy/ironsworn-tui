"""Endure Harm and Endure Stress: damage before the roll, the higher of two values, fate choices."""

import random

import pytest

from ironsworn_tui.rules.dice import Hit
from ironsworn_tui.rules.errors import RulesError
from ironsworn_tui.rules.suffer import (
    ENDURE_HARM_TABLE,
    ENDURE_STRESS_TABLE,
    evaluate_endure_harm,
    evaluate_endure_stress,
    roll_endure_harm,
    roll_endure_stress,
)


def test_harm_spills_to_momentum():
    r = evaluate_endure_harm(
        health=3, iron=2, harm=5, momentum=4, action_die=3, challenge_dice=(5, 9)
    )
    assert r.meter_after == 0
    assert r.momentum_after == 2
    assert r.spill == 2


def test_no_spill_when_health_absorbs_all():
    r = evaluate_endure_harm(
        health=5, iron=2, harm=2, momentum=4, action_die=3, challenge_dice=(5, 9)
    )
    assert r.meter_after == 3
    assert r.momentum_after == 4
    assert r.spill == 0


def test_spill_stops_at_momentum_minimum():
    r = evaluate_endure_harm(
        health=0, iron=2, harm=5, momentum=-4, action_die=3, challenge_dice=(5, 9)
    )
    assert r.momentum_after == -6
    assert r.spill == 5
    assert r.setback == 3


def test_no_setback_above_momentum_minimum():
    r = evaluate_endure_harm(
        health=3, iron=2, harm=5, momentum=4, action_die=3, challenge_dice=(5, 9)
    )
    assert r.setback == 0


def test_rolls_with_health_when_it_is_higher():
    r = evaluate_endure_harm(
        health=5, iron=2, harm=1, momentum=4, action_die=3, challenge_dice=(5, 9)
    )
    assert r.stat == "health"
    assert r.roll.value == 4


def test_rolls_with_iron_when_health_is_lower():
    r = evaluate_endure_harm(
        health=1, iron=2, harm=1, momentum=4, action_die=3, challenge_dice=(5, 9)
    )
    assert r.stat == "iron"
    assert r.roll.value == 2


def test_roll_uses_momentum_after_spill_for_cancellation():
    r = evaluate_endure_harm(
        health=0, iron=2, harm=3, momentum=0, action_die=3, challenge_dice=(5, 9)
    )
    assert r.momentum_after == -3
    assert r.roll.action_die_cancelled is True


def test_miss_at_zero_health_triggers_fate():
    r = evaluate_endure_harm(
        health=1, iron=1, harm=1, momentum=0, action_die=1, challenge_dice=(9, 10)
    )
    assert r.meter_after == 0
    assert r.roll.hit is Hit.MISS
    assert r.fate_triggered is True
    assert r.fate_table_id == ENDURE_HARM_TABLE == "classic/suffer/endure_harm/endure_harm"


def test_miss_with_health_remaining_does_not_trigger_fate():
    r = evaluate_endure_harm(
        health=5, iron=1, harm=1, momentum=0, action_die=1, challenge_dice=(9, 10)
    )
    assert r.meter_after == 4
    assert r.fate_triggered is False


def test_burning_momentum_on_the_roll_clears_the_fate_trigger():
    r = evaluate_endure_harm(
        health=1, iron=1, harm=1, momentum=9, action_die=1, challenge_dice=(4, 8)
    )
    assert r.fate_triggered is True
    assert r.roll.burn_available is True
    burned = r.burn()
    assert burned.roll.hit is Hit.STRONG
    assert burned.fate_triggered is False


def test_stress_spill_and_higher_value():
    r = evaluate_endure_stress(
        spirit=2, heart=3, stress=4, momentum=4, action_die=3, challenge_dice=(5, 9)
    )
    assert r.meter == "spirit"
    assert r.meter_after == 0
    assert r.spill == 2
    assert r.stat == "heart"
    assert r.roll.value == 3


def test_stress_miss_at_zero_triggers_fate():
    r = evaluate_endure_stress(
        spirit=1, heart=1, stress=1, momentum=0, action_die=1, challenge_dice=(9, 10)
    )
    assert r.meter_after == 0
    assert r.fate_triggered is True
    assert r.fate_table_id == ENDURE_STRESS_TABLE == "classic/suffer/endure_stress/endure_stress"


@pytest.mark.parametrize(
    ("health", "iron", "harm"),
    [(-1, 2, 1), (6, 2, 1), (3, -1, 1), (3, 2, -1)],
)
def test_bad_values_rejected(health: int, iron: int, harm: int):
    with pytest.raises(RulesError):
        evaluate_endure_harm(
            health=health, iron=iron, harm=harm, momentum=2, action_die=1, challenge_dice=(1, 1)
        )


def test_roll_endure_harm_uses_the_rng():
    r = roll_endure_harm(health=5, iron=2, harm=1, momentum=2, rng=random.Random(11))
    expected = random.Random(11)
    assert r.roll.action_die == expected.randint(1, 6)


def test_harm_with_momentum_already_at_minimum():
    r = evaluate_endure_harm(
        health=0, iron=2, harm=2, momentum=-6, action_die=3, challenge_dice=(5, 9)
    )
    assert r.momentum_after == -6
    assert r.setback == 2


def test_zero_harm_changes_nothing():
    r = evaluate_endure_harm(
        health=3, iron=2, harm=0, momentum=2, action_die=3, challenge_dice=(5, 9)
    )
    assert (r.meter_after, r.momentum_after, r.spill, r.setback) == (3, 2, 0, 0)


def test_stress_rolls_with_spirit_when_it_is_higher():
    r = evaluate_endure_stress(
        spirit=5, heart=2, stress=1, momentum=2, action_die=3, challenge_dice=(5, 9)
    )
    assert r.stat == "spirit"
    assert r.roll.value == 4


def test_stress_spill_stops_at_momentum_minimum():
    r = evaluate_endure_stress(
        spirit=1, heart=2, stress=4, momentum=-5, action_die=3, challenge_dice=(5, 9)
    )
    assert r.momentum_after == -6
    assert r.setback == 2


def test_bad_stress_values_rejected():
    with pytest.raises(RulesError):
        evaluate_endure_stress(
            spirit=2, heart=6, stress=1, momentum=2, action_die=1, challenge_dice=(1, 1)
        )


def test_roll_endure_stress_uses_the_rng():
    r = roll_endure_stress(spirit=5, heart=2, stress=1, momentum=2, rng=random.Random(11))
    expected = random.Random(11)
    assert r.roll.action_die == expected.randint(1, 6)
