"""Questions typed after `/oracle` with no table: the suggestion, the roll, and the case."""

from pathlib import Path

import pytest

from ironsworn_tui.cases import ABSTAINED, CORRECTED, ORACLE_SUITE
from ironsworn_tui.commands import run_command
from ironsworn_tui.decide import DecideError, Decision, JsonObject, OracleDecision
from ironsworn_tui.oracles import ASKED_TABLES, LIKELIHOOD_OPTIONS
from tests.support import engine

CASTLE = "Do I know which castle I'm in?"


class Sink:
    def __init__(self) -> None:
        self.saved: list[tuple[str, JsonObject]] = []

    def add_case(self, suite: str, case: JsonObject) -> None:
        self.saved.append((suite, case))


class Down:
    def decide(self, request: JsonObject, target: str) -> Decision:
        raise DecideError("jevtester isn't reachable")

    def decide_oracle(self, request: JsonObject, target: str) -> OracleDecision:
        raise DecideError("jevtester isn't reachable")


def test_the_request_carries_the_question_and_scene(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    turn.campaign.situation = "A stone cell."
    decider.oracle_answers.append(("yes_no", "unlikely", 0.9))
    turn.suggest_oracle(CASTLE)
    assert decider.requests[0]["state"] == {
        "character": "Kira, a hunter",
        "situation": "A stone cell.",
        "question": CASTLE,
    }


def test_a_confident_yes_no_answer_preselects_the_likelihood(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    decider.oracle_answers.append(("yes_no", "unlikely", 0.9))
    suggestion = turn.suggest_oracle(CASTLE)
    assert suggestion.band == "act"
    assert suggestion.question == CASTLE
    assert suggestion.options[0] == "unlikely"
    assert set(suggestion.options[:5]) == set(LIKELIHOOD_OPTIONS)
    assert set(suggestion.options[5:]) == set(ASKED_TABLES)


def test_a_confident_table_answer_puts_the_tables_first(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    decider.oracle_answers.append(("table", "location", 0.9))
    suggestion = turn.suggest_oracle("What do I find over the hill?")
    assert suggestion.band == "act"
    assert suggestion.options[0] == "location"
    assert set(suggestion.options[: len(ASKED_TABLES)]) == set(ASKED_TABLES)


def test_a_low_probability_table_preselects_nothing(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    decider.oracle_answers.append(("table", "location", 0.3))
    suggestion = turn.suggest_oracle("What do I find over the hill?")
    assert suggestion.band == "escalate"
    assert suggestion.options[0] == "location"


def test_cannot_tell_offers_the_full_list(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    decider.oracle_answers.append(("cannot_tell", "", 0.9))
    suggestion = turn.suggest_oracle("Remember to buy rope")
    assert suggestion.band == "escalate"
    assert suggestion.options == (*ASKED_TABLES, *LIKELIHOOD_OPTIONS)


def test_a_failed_request_offers_the_full_list_and_says_why(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.decider = Down()
    suggestion = turn.suggest_oracle(CASTLE)
    assert suggestion.band == "escalate"
    assert suggestion.options == (*ASKED_TABLES, *LIKELIHOOD_OPTIONS)
    assert turn.campaign.log[-1].text == "No suggestion: jevtester isn't reachable"


def test_without_a_decider_the_full_list_is_offered(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.decider = None
    assert turn.suggest_oracle(CASTLE).options == (*ASKED_TABLES, *LIKELIHOOD_OPTIONS)


def test_answering_with_a_likelihood_asks_the_oracle_and_logs_the_question(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.oracle_answers.append(("yes_no", "unlikely", 0.9))
    turn.suggest_oracle(CASTLE)
    dice.load(80)
    turn.answer_oracle("unlikely", CASTLE)
    assert turn.campaign.log[-1].text == f"Ask (unlikely): {CASTLE} 80: yes"


def test_answering_with_a_table_rolls_it_and_logs_the_question(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.oracle_answers.append(("table", "action", 0.9))
    turn.suggest_oracle("What happens next?")
    dice.load(2)
    turn.answer_oracle("action", "What happens next?")
    assert turn.campaign.log[-1].text == "Oracle (action): What happens next? 2: Clash"


def test_an_answered_question_is_saved_as_a_case(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    sink = Sink()
    turn.cases = sink
    decider.oracle_answers.append(("yes_no", "unlikely", 0.9))
    turn.suggest_oracle(CASTLE)
    dice.load(80)
    turn.answer_oracle("unlikely", CASTLE)
    decider.oracle_answers.append(("yes_no", "likely", 0.9))
    turn.suggest_oracle("Is the bridge guarded?")
    dice.load(2)
    turn.answer_oracle("location", "Is the bridge guarded?")
    decider.oracle_answers.append(("cannot_tell", "", 0.9))
    turn.suggest_oracle("Remember to buy rope")
    dice.load(1)
    turn.answer_oracle("theme", "Remember to buy rope")

    assert [suite for suite, _ in sink.saved] == [ORACLE_SUITE] * 3
    first, second, third = (case for _, case in sink.saved)
    assert first["state"]["question"] == CASTLE
    assert first["expected"] == {"kind": {"answer": "yes_no"}, "likelihood": {"answer": "unlikely"}}
    assert first["expected_action"] == "unlikely"
    assert first["tags"] == []
    assert second["expected"] == {"kind": {"answer": "table"}, "table": {"answer": "location"}}
    assert second["tags"] == [CORRECTED]
    assert third["tags"] == [ABSTAINED]


def test_skipping_saves_nothing(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    sink = Sink()
    turn.cases = sink
    decider.oracle_answers.append(("yes_no", "unlikely", 0.9))
    turn.suggest_oracle(CASTLE)
    turn.skip_oracle()
    dice.load(80)
    turn.answer_oracle("unlikely", CASTLE)
    assert sink.saved == []


def test_a_failed_request_is_not_saved(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    sink = Sink()
    turn.cases = sink
    turn.decider = Down()
    turn.suggest_oracle(CASTLE)
    dice.load(80)
    turn.answer_oracle("unlikely", CASTLE)
    assert sink.saved == []


def test_an_unknown_option_is_refused(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(ValueError, match="weather"):
        turn.answer_oracle("weather", CASTLE)


def test_oracle_with_a_question_and_no_table_asks_the_model(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    result = run_command(turn, f"/oracle {CASTLE}")
    assert result.oracle_question == CASTLE


def test_oracle_alone_offers_the_full_list(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert run_command(turn, "/oracle").oracle_question == ""


def test_oracle_with_a_table_still_rolls_it(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(2)
    result = run_command(turn, "/oracle action What does the stranger want?")
    assert result.oracle_question is None
    assert turn.campaign.log[-1].text == "Oracle (action): What does the stranger want? 2: Clash"
