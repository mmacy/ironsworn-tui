"""Action rolls: hit math, the score cap, die cancellation, burning momentum, and matches."""

import random

import pytest

from ironsworn_tui.rules.action import burn_momentum, evaluate_action, roll_action
from ironsworn_tui.rules.dice import Hit, hit_for
from ironsworn_tui.rules.errors import RulesError


def test_strong_hit():
    r = evaluate_action(value=3, adds=1, momentum=2, action_die=5, challenge_dice=(4, 8))
    assert r.score == 9
    assert r.hit is Hit.STRONG
    assert r.match is False


def test_weak_hit():
    r = evaluate_action(value=3, adds=0, momentum=2, action_die=5, challenge_dice=(4, 9))
    assert r.hit is Hit.WEAK


def test_miss():
    r = evaluate_action(value=1, adds=0, momentum=2, action_die=2, challenge_dice=(7, 9))
    assert r.hit is Hit.MISS


def test_tie_with_a_challenge_die_does_not_beat_it():
    r = evaluate_action(value=2, adds=0, momentum=2, action_die=4, challenge_dice=(6, 3))
    assert r.score == 6
    assert r.hit is Hit.WEAK


def test_action_score_capped_at_10():
    r = evaluate_action(value=5, adds=4, momentum=2, action_die=6, challenge_dice=(3, 3))
    assert r.raw_score == 15
    assert r.score == 10
    assert r.capped is True


def test_negative_momentum_cancels_matching_action_die():
    r = evaluate_action(value=3, adds=0, momentum=-3, action_die=3, challenge_dice=(2, 4))
    assert r.action_die_cancelled is True
    assert r.score == 3
    assert r.hit is Hit.WEAK


def test_negative_momentum_no_cancel_when_die_differs():
    r = evaluate_action(value=3, adds=0, momentum=-3, action_die=4, challenge_dice=(2, 4))
    assert r.action_die_cancelled is False
    assert r.score == 7


def test_positive_momentum_never_cancels():
    r = evaluate_action(value=3, adds=0, momentum=3, action_die=3, challenge_dice=(2, 4))
    assert r.action_die_cancelled is False


def test_burn_upgrades_hit():
    r = evaluate_action(value=0, adds=0, momentum=8, action_die=1, challenge_dice=(5, 7))
    assert r.hit is Hit.MISS
    burned = burn_momentum(r)
    assert burned.burned is True
    assert burned.hit is Hit.STRONG
    assert burned.challenge_dice == (5, 7)
    assert burned.action_die == 1


def test_burn_never_makes_the_result_worse():
    r = evaluate_action(value=3, adds=0, momentum=3, action_die=6, challenge_dice=(2, 8))
    assert r.hit is Hit.STRONG
    assert r.burn_available is False
    assert burn_momentum(r).hit is Hit.STRONG


def test_burn_cancels_only_dice_below_momentum():
    r = evaluate_action(value=0, adds=0, momentum=6, action_die=4, challenge_dice=(5, 8))
    assert r.hit is Hit.MISS
    assert burn_momentum(r).hit is Hit.WEAK


def test_burn_cancels_a_die_the_score_did_not_beat():
    r = evaluate_action(value=4, adds=0, momentum=8, action_die=1, challenge_dice=(3, 7))
    assert r.hit is Hit.WEAK
    assert burn_momentum(r).hit is Hit.STRONG


def test_burn_available_without_burning():
    r = evaluate_action(value=2, adds=0, momentum=9, action_die=1, challenge_dice=(6, 8))
    assert r.hit is Hit.MISS
    assert r.burn_available is True


def test_burn_not_available_when_it_does_not_improve():
    r = evaluate_action(value=3, adds=0, momentum=5, action_die=4, challenge_dice=(6, 8))
    assert r.hit is Hit.WEAK
    assert r.burn_available is False


def test_burn_not_available_with_no_positive_momentum():
    r = evaluate_action(value=0, adds=0, momentum=0, action_die=1, challenge_dice=(9, 9))
    assert r.burn_available is False
    with pytest.raises(RulesError):
        burn_momentum(r)


def test_burn_not_available_after_burning():
    r = evaluate_action(value=0, adds=0, momentum=6, action_die=1, challenge_dice=(5, 7))
    burned = burn_momentum(r)
    assert burned.hit is Hit.WEAK
    assert burned.burn_available is False
    with pytest.raises(RulesError):
        burn_momentum(burned)


def test_matched_challenge_dice():
    r = evaluate_action(value=3, adds=0, momentum=2, action_die=5, challenge_dice=(7, 7))
    assert r.match is True


def test_matched_tens():
    r = evaluate_action(value=3, adds=0, momentum=2, action_die=5, challenge_dice=(10, 10))
    assert r.match is True
    assert r.hit is Hit.MISS


@pytest.mark.parametrize("action_die", [0, 7])
def test_action_die_out_of_range_rejected(action_die: int):
    with pytest.raises(RulesError):
        evaluate_action(value=1, adds=0, momentum=2, action_die=action_die, challenge_dice=(1, 1))


@pytest.mark.parametrize("challenge_dice", [(0, 5), (5, 11)])
def test_challenge_dice_out_of_range_rejected(challenge_dice: tuple[int, int]):
    with pytest.raises(RulesError):
        evaluate_action(value=1, adds=0, momentum=2, action_die=1, challenge_dice=challenge_dice)


@pytest.mark.parametrize("momentum", [-7, 11])
def test_momentum_out_of_range_rejected(momentum: int):
    with pytest.raises(RulesError):
        evaluate_action(value=1, adds=0, momentum=momentum, action_die=1, challenge_dice=(1, 1))


def test_roll_action_uses_the_rng_for_every_die():
    r = roll_action(value=2, adds=1, momentum=2, rng=random.Random(7))
    expected = random.Random(7)
    action_die = expected.randint(1, 6)
    challenge_dice = (expected.randint(1, 10), expected.randint(1, 10))
    assert r.action_die == action_die
    assert r.challenge_dice == challenge_dice


def test_hit_for_ranks():
    assert hit_for(5, (4, 4)) is Hit.STRONG
    assert hit_for(5, (5, 4)) is Hit.WEAK
    assert hit_for(5, (5, 5)) is Hit.MISS
    assert Hit.MISS < Hit.WEAK < Hit.STRONG
