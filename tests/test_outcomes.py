"""The outcome table, checked against the move text."""

import re

import pytest

from ironsworn_tui.moves import Initiative, MoveGroup, move_group
from ironsworn_tui.outcomes import (
    OUTCOMES,
    Choose,
    ClearDebility,
    Effect,
    FollowUp,
    MarkProgress,
    MeterChange,
    Momentum,
    MoveDetails,
    Note,
    SetInitiative,
    outcome,
)
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.dice import Hit


def _flatten(effects: tuple[Effect, ...]) -> list[Effect]:
    flat: list[Effect] = []
    for effect in effects:
        if isinstance(effect, Choose):
            for option in effect.options:
                flat += _flatten(option.effects)
        else:
            flat.append(effect)
    return flat


def _text(move: str) -> str:
    """The move's text and its results' text. An asset move's text leaves out its miss."""
    data = datasworn().find_move(move)
    parts = [data.text]
    if data.outcomes is not None:
        parts += [
            data.outcomes.strong_hit.text,
            data.outcomes.weak_hit.text,
            data.outcomes.miss.text,
        ]
    return re.sub(r"\[([^\]]+)\]\(datasworn:[^)]+\)", r"\1", " ".join(parts))


def test_every_move_that_rolls_from_the_chat_has_an_entry():
    data = datasworn()
    for move_id, move in data.moves.items():
        if move_group(data, move_id) is MoveGroup.FICTION and move.roll_type != "no_roll":
            assert move_id in OUTCOMES, move_id
    assert {"end_the_fight", "endure_harm", "endure_stress"} <= set(OUTCOMES)
    assert all(data.find_move(move_id).roll_type != "no_roll" for move_id in OUTCOMES)


@pytest.mark.parametrize("move", sorted(OUTCOMES))
@pytest.mark.parametrize("hit", list(Hit))
def test_every_result_has_an_entry(move: str, hit: Hit):
    assert isinstance(outcome(move, hit), tuple)


# Amounts the table derives from the text instead of quoting it.
DERIVED = {
    ("resupply", "-2 momentum"),
    ("resupply", "+1 supply"),
    ("draw_the_circle", "+1 momentum"),
}


def _result_text(move: str, hit: Hit) -> str:
    outcomes = datasworn().find_move(move).outcomes
    assert outcomes is not None
    result = {Hit.STRONG: outcomes.strong_hit, Hit.WEAK: outcomes.weak_hit, Hit.MISS: outcomes.miss}
    return re.sub(r"\[([^\]]+)\]\(datasworn:[^)]+\)", r"\1", result[hit].text)


@pytest.mark.parametrize("move", sorted(OUTCOMES))
def test_amounts_appear_in_their_result_text(move: str):
    for hit in Hit:
        text = _result_text(move, hit)
        for effect in _flatten(outcome(move, hit)):
            if isinstance(effect, Momentum):
                phrase = f"{effect.amount:+d} momentum"
            elif isinstance(effect, MeterChange):
                phrase = f"{effect.amount:+d} {effect.meter}"
            else:
                continue
            if (move, phrase) not in DERIVED:
                assert phrase in text, f"{move} {hit.label}: {phrase!r} isn't in the move text"


@pytest.mark.parametrize("move", sorted(OUTCOMES))
def test_follow_ups_appear_in_the_move_text(move: str):
    names = {
        "pay_the_price": "Pay the Price",
        "endure_harm": "Endure Harm",
        "endure_stress": "Endure Stress",
        "forsake_your_vow": "Forsake Your Vow",
    }
    text = _text(move)
    for hit in Hit:
        for effect in _flatten(outcome(move, hit)):
            if isinstance(effect, FollowUp):
                assert names[effect.move] in text


@pytest.mark.parametrize(
    ("move", "hit", "initiative"),
    [
        ("strike", Hit.STRONG, "character"),
        ("strike", Hit.WEAK, "foe"),
        ("strike", Hit.MISS, "foe"),
        ("clash", Hit.STRONG, "character"),
        ("clash", Hit.WEAK, "foe"),
        ("enter_the_fray", Hit.STRONG, "character"),
        ("enter_the_fray", Hit.MISS, "foe"),
    ],
)
def test_initiative_changes(move: str, hit: Hit, initiative: Initiative):
    assert SetInitiative(initiative) in outcome(move, hit)


@pytest.mark.parametrize("harm", [1, 2])
def test_strike_strong_hit_inflicts_one_more_harm(harm: int):
    details = MoveDetails(harm=harm)
    assert MarkProgress("target", times=harm + 1) in outcome("strike", Hit.STRONG, details)
    assert MarkProgress("target", times=harm) in outcome("strike", Hit.WEAK, details)


def test_heal_on_yourself_clears_wounded_and_takes_health():
    effects = outcome("heal", Hit.STRONG, MoveDetails(heal_self=True))
    assert effects[:2] == (ClearDebility("wounded"), MeterChange("health", 2))
    other = outcome("heal", Hit.STRONG, MoveDetails(heal_self=False))
    assert isinstance(other[0], Note)


def test_shake_it_off_needs_the_meter_above_zero():
    labels = [
        o.label
        for e in outcome("endure_harm", Hit.STRONG)
        if isinstance(e, Choose)
        for o in e.options
    ]
    assert any(label.startswith("Shake it off") for label in labels)
    at_zero = outcome("endure_harm", Hit.STRONG, MoveDetails(meter_above_zero=False))
    labels = [o.label for e in at_zero if isinstance(e, Choose) for o in e.options]
    assert not any(label.startswith("Shake it off") for label in labels)


def test_misses_on_most_moves_pay_the_price():
    for move in ("face_danger", "secure_an_advantage", "gather_information", "compel", "strike"):
        assert FollowUp("pay_the_price") in outcome(move, Hit.MISS)
