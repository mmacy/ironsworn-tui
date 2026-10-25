"""Progress tracks: ticks per rank, bonds, and progress rolls."""

import random

import pytest

from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.dice import Hit
from ironsworn_tui.rules.errors import RulesError
from ironsworn_tui.rules.progress import (
    BOND_TICKS,
    Rank,
    evaluate_progress,
    npc_rank,
    roll_progress,
)


@pytest.mark.parametrize(
    ("rank", "expected_ticks"),
    [
        (Rank.TROUBLESOME, 12),
        (Rank.DANGEROUS, 8),
        (Rank.FORMIDABLE, 4),
        (Rank.EXTREME, 2),
        (Rank.EPIC, 1),
    ],
)
def test_ticks_per_rank(rank: Rank, expected_ticks: int):
    assert rank.ticks == expected_ticks


def test_harm_equals_rank_value():
    assert [rank.harm for rank in Rank] == [1, 2, 3, 4, 5]


def test_bond_always_one_tick():
    assert BOND_TICKS == 1


def test_progress_roll_uses_boxes_not_ticks():
    r = evaluate_progress(ticks=16, challenge_dice=(3, 7))
    assert r.score == 4
    assert r.hit is Hit.WEAK


def test_progress_roll_full_track_strong():
    r = evaluate_progress(ticks=40, challenge_dice=(5, 9))
    assert r.score == 10
    assert r.hit is Hit.STRONG


def test_progress_roll_partial_box_floors():
    r = evaluate_progress(ticks=11, challenge_dice=(1, 5))
    assert r.score == 2
    assert r.hit is Hit.WEAK


def test_progress_roll_match():
    r = evaluate_progress(ticks=0, challenge_dice=(4, 4))
    assert r.match is True
    assert r.hit is Hit.MISS


@pytest.mark.parametrize("ticks", [-1, 41, 100])
def test_ticks_out_of_range_rejected(ticks: int):
    with pytest.raises(RulesError):
        evaluate_progress(ticks=ticks, challenge_dice=(1, 1))


def test_roll_progress_uses_the_rng():
    r = roll_progress(ticks=20, rng=random.Random(3))
    expected = random.Random(3)
    assert r.challenge_dice == (expected.randint(1, 10), expected.randint(1, 10))


def test_npc_rank_warrior_is_dangerous():
    rank = npc_rank(datasworn(), "warrior")
    assert rank is Rank.DANGEROUS
    assert rank.harm == 2
    assert rank.ticks == 8
