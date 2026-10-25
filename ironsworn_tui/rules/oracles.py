"""The yes/no oracle and the oracle tables."""

import random
from dataclasses import dataclass
from enum import StrEnum

from ironsworn_tui.rules.datasworn import Datasworn, OracleRow, OracleTable
from ironsworn_tui.rules.dice import check_die
from ironsworn_tui.rules.errors import RulesError

SUBROLL_DEPTH_MAX = 3


class Likelihood(StrEnum):
    """The odds the player gives a yes/no question."""

    ALMOST_CERTAIN = "almost_certain"
    LIKELY = "likely"
    FIFTY_FIFTY = "50_50"
    UNLIKELY = "unlikely"
    SMALL_CHANCE = "small_chance"

    @property
    def threshold(self) -> int:
        """The lowest d100 roll that answers yes."""
        return {
            Likelihood.ALMOST_CERTAIN: 11,
            Likelihood.LIKELY: 26,
            Likelihood.FIFTY_FIFTY: 51,
            Likelihood.UNLIKELY: 76,
            Likelihood.SMALL_CHANCE: 91,
        }[self]


@dataclass(frozen=True)
class YesNo:
    """A yes/no oracle answer.

    Attributes:
        likelihood: The odds the player gave.
        roll: The d100 roll.
        yes: True when the roll is at or above the threshold.
        match: True on doubles (11, 22, ... 99) or 100, which signals an extreme result or a twist.
    """

    likelihood: Likelihood
    roll: int
    yes: bool
    match: bool


def evaluate_yes_no(likelihood: Likelihood, roll: int) -> YesNo:
    """Answer a yes/no question from a d100 roll that's already rolled.

    Args:
        likelihood: The odds the player gave.
        roll: The d100 result.

    Returns:
        The answer and whether the roll was a match.

    Raises:
        RulesError: If `roll` is outside 1 to 100.
    """
    check_die(roll, 100, "the oracle roll")
    match = roll == 100 or roll % 11 == 0
    return YesNo(likelihood=likelihood, roll=roll, yes=roll >= likelihood.threshold, match=match)


def ask_yes_no(likelihood: Likelihood, rng: random.Random) -> YesNo:
    """Roll a d100 and answer a yes/no question."""
    return evaluate_yes_no(likelihood, rng.randint(1, 100))


@dataclass(frozen=True)
class OracleResult:
    """A roll on an oracle table.

    Attributes:
        table_id: The table's oracle id.
        sides: The die size the table uses.
        roll: The roll.
        text: The text of the row the roll landed on.
        subrolls: Further rolls the row called for, such as "Roll twice more on this table".
        make_it_worse: True when the row said to make the result worse if its further rolls
            matched, and they landed on the same row.
        truncated: True when the row called for further rolls that weren't made, because the
            rolls were already three levels deep.
    """

    table_id: str
    sides: int
    roll: int
    text: str
    subrolls: tuple[OracleResult, ...] = ()
    make_it_worse: bool = False
    truncated: bool = False


def table_sides(table: OracleTable) -> int:
    """Return the die size for a table, from the highest value on its rows."""
    highest = max((row.roll.max for row in table.rows if row.roll), default=100)
    for sides in (6, 10, 20, 36):
        if highest <= sides:
            return sides
    return 100


def _find_row(table: OracleTable, roll: int) -> OracleRow | None:
    for row in table.rows:
        if row.roll and row.roll.min <= roll <= row.roll.max:
            return row
    return None


def roll_oracle(
    data: Datasworn, table_id: str, rng: random.Random, roll: int | None = None
) -> OracleResult:
    """Roll on an oracle table, including any further rolls the row calls for.

    Further rolls go at most three levels deep. Rolls Datasworn doesn't mark as automatic are
    made too, because they're examples the player can use or ignore.

    Args:
        data: The Datasworn data.
        table_id: The table's full oracle id, such as `classic/action_and_theme/action`.
        rng: The source of the rolls.
        roll: The first roll, when it's already rolled. Further rolls always use `rng`.

    Raises:
        UnknownIdError: If no table has the id.
        RulesError: If `roll` is outside the table's die, or no row covers it.
    """
    return _roll_table(data, table_id, data.oracle(table_id), rng, roll, depth=0)


def _roll_table(
    data: Datasworn,
    table_id: str,
    table: OracleTable,
    rng: random.Random,
    roll: int | None,
    depth: int,
) -> OracleResult:
    sides = table_sides(table)
    if roll is None:
        roll = rng.randint(1, sides)
    check_die(roll, sides, "the oracle roll")
    row = _find_row(table, roll)
    if row is None:
        raise RulesError(f"no row of {table_id} covers {roll}")

    subrolls: list[OracleResult] = []
    make_it_worse = False
    truncated = bool(row.oracle_rolls) and depth >= SUBROLL_DEPTH_MAX
    if not truncated:
        for directive in row.oracle_rolls:
            target_id = directive.table_id or table_id
            target = data.oracle(target_id)
            target_sides = table_sides(target)
            results: list[OracleResult] = []
            for _ in range(directive.number_of_rolls):
                sub_roll = rng.randint(1, target_sides)
                while directive.duplicates == "reroll" and _same_row(target, sub_roll, results):
                    sub_roll = rng.randint(1, target_sides)
                results.append(_roll_table(data, target_id, target, rng, sub_roll, depth + 1))
            rows = {result.text for result in results}
            if directive.duplicates == "make_it_worse" and len(rows) < len(results):
                make_it_worse = True
            subrolls.extend(results)

    return OracleResult(
        table_id=table_id,
        sides=sides,
        roll=roll,
        text=row.text,
        subrolls=tuple(subrolls),
        make_it_worse=make_it_worse,
        truncated=truncated,
    )


def _same_row(table: OracleTable, roll: int, results: list[OracleResult]) -> bool:
    row = _find_row(table, roll)
    return row is not None and any(result.text == row.text for result in results)
