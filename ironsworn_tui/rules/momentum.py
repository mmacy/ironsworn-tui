"""Momentum limits and the momentum reset."""

from dataclasses import dataclass

from ironsworn_tui.rules.errors import RulesError

MOMENTUM_MIN = -6
MOMENTUM_MAX = 10


@dataclass(frozen=True)
class MomentumBounds:
    """The momentum range and reset value for a number of debilities.

    Attributes:
        min: The lowest momentum, always -6.
        max: The highest momentum, 10 minus the number of debilities.
        reset: The value momentum resets to after it's burned: +2 with no debilities, +1 with
            one, and 0 with two or more.
    """

    min: int
    max: int
    reset: int


def momentum_bounds(debilities: int) -> MomentumBounds:
    """Return the momentum range and reset for a number of marked debilities.

    Args:
        debilities: How many debilities the character has marked.

    Returns:
        The minimum, maximum, and reset.

    Raises:
        RulesError: If `debilities` is negative.
    """
    if debilities < 0:
        raise RulesError(f"debilities must be non-negative, got {debilities}")
    reset = max(0, 2 - debilities)
    return MomentumBounds(min=MOMENTUM_MIN, max=max(0, MOMENTUM_MAX - debilities), reset=reset)


@dataclass(frozen=True)
class MomentumChange:
    """Momentum after a gain or loss.

    Attributes:
        momentum: The new momentum, within the bounds.
        setback: The loss that would have taken momentum below -6. The rulebook turns it into
            the Face a Setback move.
    """

    momentum: int
    setback: int


def adjust_momentum(momentum: int, delta: int, maximum: int = MOMENTUM_MAX) -> MomentumChange:
    """Add a gain or loss to momentum, within -6 and the maximum.

    Args:
        momentum: The current momentum.
        delta: The gain (positive) or loss (negative).
        maximum: The highest momentum, which debilities lower. See
            [`momentum_bounds`][ironsworn_tui.rules.momentum.momentum_bounds].

    Returns:
        The new momentum and any loss past the minimum.

    Raises:
        RulesError: If `momentum` is out of range.
    """
    check_momentum(momentum)
    target = momentum + delta
    return MomentumChange(
        momentum=max(MOMENTUM_MIN, min(target, maximum)),
        setback=max(0, MOMENTUM_MIN - target),
    )


def check_momentum(momentum: int) -> None:
    """Raise if momentum is outside -6 to +10.

    Raises:
        RulesError: If `momentum` is out of range.
    """
    if not MOMENTUM_MIN <= momentum <= MOMENTUM_MAX:
        raise RulesError(f"momentum must be {MOMENTUM_MIN} to {MOMENTUM_MAX}, got {momentum}")
