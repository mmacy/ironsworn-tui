"""Momentum bounds derived from debilities."""

import pytest

from ironsworn_tui.rules.errors import RulesError
from ironsworn_tui.rules.momentum import MOMENTUM_MIN, adjust_momentum, momentum_bounds


@pytest.mark.parametrize(
    ("debilities", "expected_max", "expected_reset"),
    [(0, 10, 2), (1, 9, 1), (2, 8, 0), (3, 7, 0), (4, 6, 0), (8, 2, 0)],
)
def test_momentum_bounds(debilities: int, expected_max: int, expected_reset: int):
    bounds = momentum_bounds(debilities)
    assert bounds.max == expected_max
    assert bounds.reset == expected_reset
    assert bounds.min == MOMENTUM_MIN == -6


def test_negative_debilities_rejected():
    with pytest.raises(RulesError):
        momentum_bounds(-1)


@pytest.mark.parametrize(
    ("momentum", "delta", "maximum", "expected", "setback"),
    [
        (2, 1, 10, 3, 0),
        (9, 3, 10, 10, 0),
        (7, 2, 8, 8, 0),
        (-4, -2, 10, -6, 0),
        (-4, -5, 10, -6, 3),
        (-6, -1, 10, -6, 1),
    ],
)
def test_adjust_momentum(momentum: int, delta: int, maximum: int, expected: int, setback: int):
    change = adjust_momentum(momentum, delta, maximum)
    assert change.momentum == expected
    assert change.setback == setback


def test_adjust_momentum_rejects_out_of_range_start():
    with pytest.raises(RulesError):
        adjust_momentum(-7, 1)
