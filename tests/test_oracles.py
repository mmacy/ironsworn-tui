"""Yes/no oracle and table oracles."""

import dataclasses
import random

import pytest

from ironsworn_tui.rules.datasworn import OracleRow, OracleTable, RollRange, datasworn
from ironsworn_tui.rules.errors import RulesError, UnknownIdError
from ironsworn_tui.rules.oracles import (
    Likelihood,
    ask_yes_no,
    evaluate_yes_no,
    roll_oracle,
    table_sides,
)

PAY_THE_PRICE = "classic/fate/pay_the_price/pay_the_price"


@pytest.mark.parametrize(
    ("likelihood", "threshold"),
    [
        (Likelihood.ALMOST_CERTAIN, 11),
        (Likelihood.LIKELY, 26),
        (Likelihood.FIFTY_FIFTY, 51),
        (Likelihood.UNLIKELY, 76),
        (Likelihood.SMALL_CHANCE, 91),
    ],
)
def test_yes_no_threshold(likelihood: Likelihood, threshold: int):
    assert likelihood.threshold == threshold
    assert evaluate_yes_no(likelihood, threshold).yes is True
    assert evaluate_yes_no(likelihood, threshold - 1).yes is False


def test_almost_certain_roll_11_is_yes_with_match():
    r = evaluate_yes_no(Likelihood.ALMOST_CERTAIN, 11)
    assert r.yes is True
    assert r.match is True


@pytest.mark.parametrize("roll", [11, 22, 33, 44, 55, 66, 77, 88, 99, 100])
def test_yes_no_match_on_doubles(roll: int):
    assert evaluate_yes_no(Likelihood.FIFTY_FIFTY, roll).match is True


@pytest.mark.parametrize("roll", [1, 10, 12, 50, 98])
def test_yes_no_no_match(roll: int):
    assert evaluate_yes_no(Likelihood.FIFTY_FIFTY, roll).match is False


@pytest.mark.parametrize("roll", [0, 101])
def test_yes_no_roll_out_of_range_rejected(roll: int):
    with pytest.raises(RulesError):
        evaluate_yes_no(Likelihood.LIKELY, roll)


def test_ask_yes_no_uses_the_rng():
    r = ask_yes_no(Likelihood.LIKELY, random.Random(5))
    assert r.roll == random.Random(5).randint(1, 100)


@pytest.mark.parametrize(
    "table_id",
    [
        PAY_THE_PRICE,
        "classic/suffer/endure_harm/endure_harm",
        "classic/suffer/endure_stress/endure_stress",
        "classic/action_and_theme/action",
    ],
)
def test_tables_indexed(table_id: str):
    assert table_id in datasworn().oracles


def test_pay_the_price_row_99_rolls_twice_more():
    r = roll_oracle(datasworn(), PAY_THE_PRICE, random.Random(1), roll=99)
    assert len(r.subrolls) == 2
    for sub in r.subrolls:
        assert sub.table_id == PAY_THE_PRICE
        assert sub.text


def test_pay_the_price_row_1_does_not_recurse():
    r = roll_oracle(datasworn(), PAY_THE_PRICE, random.Random(1), roll=1)
    assert "Roll again" in r.text
    assert r.subrolls == ()


class AlwaysHigh(random.Random):
    def randint(self, a: int, b: int) -> int:
        return b


def test_subrolls_stop_at_depth_limit():
    r = roll_oracle(datasworn(), PAY_THE_PRICE, AlwaysHigh(), roll=100)
    depth = 0
    node = r
    while node.subrolls:
        assert node.truncated is False
        node = node.subrolls[0]
        depth += 1
    assert depth == 3
    assert node.truncated is True


def test_matching_subrolls_make_it_worse():
    r = roll_oracle(datasworn(), PAY_THE_PRICE, Fixed(30, 31), roll=99)
    assert r.subrolls[0].text == r.subrolls[1].text
    assert r.make_it_worse is True


def test_different_subrolls_do_not_make_it_worse():
    r = roll_oracle(datasworn(), PAY_THE_PRICE, Fixed(30, 45), roll=99)
    assert r.make_it_worse is False


class Fixed(random.Random):
    def __init__(self, *rolls: int) -> None:
        super().__init__()
        self.rolls = list(rolls)

    def randint(self, a: int, b: int) -> int:
        return self.rolls.pop(0)


@pytest.mark.parametrize("table_id", sorted(datasworn().oracles))
def test_every_table_covers_its_die_and_every_target_resolves(table_id: str):
    data = datasworn()
    table = data.oracle(table_id)
    covered = sorted(
        value for row in table.rows if row.roll for value in range(row.roll.min, row.roll.max + 1)
    )
    assert covered == list(range(1, table_sides(table) + 1))
    for row in table.rows:
        for directive in row.oracle_rolls:
            if directive.table_id is not None:
                data.oracle(directive.table_id)


def test_endure_harm_row_5_is_mortal():
    r = roll_oracle(datasworn(), "classic/suffer/endure_harm/endure_harm", random.Random(), roll=5)
    assert "mortal" in r.text.lower()


def test_endure_stress_row_5_has_text():
    r = roll_oracle(
        datasworn(), "classic/suffer/endure_stress/endure_stress", random.Random(), roll=5
    )
    assert r.text


def test_table_sides():
    data = datasworn()
    assert table_sides(data.oracle(PAY_THE_PRICE)) == 100
    assert table_sides(_table(6)) == 6
    assert table_sides(_table(10)) == 10
    assert table_sides(_table(20)) == 20
    assert table_sides(_table(36)) == 36


def _table(highest: int) -> OracleTable:
    return OracleTable(name="Test", rows=(OracleRow(roll=RollRange(min=1, max=highest)),))


def test_directive_to_another_table_rolls_that_table():
    r = roll_oracle(datasworn(), "classic/settlement/name", random.Random(4), roll=1)
    assert len(r.subrolls) == 1
    assert r.subrolls[0].table_id == "classic/settlement/name/landscape_feature"


def test_row_with_no_match_rejected():
    gappy = OracleTable(
        name="Gappy",
        rows=(
            OracleRow(roll=RollRange(min=1, max=50), text="Low"),
            OracleRow(roll=RollRange(min=60, max=100), text="High"),
        ),
    )
    data = dataclasses.replace(datasworn(), oracles={"test/gappy": gappy})
    with pytest.raises(RulesError):
        roll_oracle(data, "test/gappy", random.Random(), roll=55)


def test_oracle_roll_out_of_range_rejected():
    with pytest.raises(RulesError):
        roll_oracle(datasworn(), PAY_THE_PRICE, random.Random(), roll=101)


def test_unknown_oracle_id_rejected():
    with pytest.raises(UnknownIdError):
        roll_oracle(datasworn(), "bogus/id", random.Random())
