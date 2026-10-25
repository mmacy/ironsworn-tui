"""The oracle request: what kind of answer a question wants, the likelihood, and the table."""

import re
from typing import Any

import pytest

from ironsworn_tui.criteria import TABLE, YES_NO
from ironsworn_tui.decide import (
    KIND_QUESTION,
    LIKELIHOOD_QUESTION,
    TABLE_QUESTION,
    DecideError,
    OracleState,
    build_oracle_request,
    parse_oracle_decision,
)
from ironsworn_tui.moves import CANNOT_TELL
from ironsworn_tui.oracles import ASKED_TABLES, LIKELIHOOD_OPTIONS, ORACLES

# The Ollama target takes at most 26 options per question.
MAX_OPTIONS = 26


def castle_state() -> OracleState:
    return OracleState(
        character="Kira, a hunter",
        situation="Kira wakes in a stone cell with no memory of the road.",
        question="Do I know which castle I'm in?",
    )


def test_state_has_the_question_and_what_it_depends_on():
    assert castle_state().to_json() == {
        "character": "Kira, a hunter",
        "situation": "Kira wakes in a stone cell with no memory of the road.",
        "question": "Do I know which castle I'm in?",
    }


def test_request_asks_three_questions_in_order():
    questions = build_oracle_request(castle_state())["questions"]
    assert list(questions) == [KIND_QUESTION, LIKELIHOOD_QUESTION, TABLE_QUESTION]
    assert all(question["type"] == "choice" for question in questions.values())


def test_kind_offers_yes_no_table_and_cannot_tell():
    kind = build_oracle_request(castle_state())["questions"][KIND_QUESTION]
    assert list(kind["criteria"]) == [YES_NO, TABLE, CANNOT_TELL]


def test_likelihood_offers_the_five_odds_most_likely_first():
    likelihood = build_oracle_request(castle_state())["questions"][LIKELIHOOD_QUESTION]
    assert list(likelihood["criteria"]) == list(LIKELIHOOD_OPTIONS)


def test_table_offers_every_table_the_player_rolls():
    table = build_oracle_request(castle_state())["questions"][TABLE_QUESTION]
    assert list(table["criteria"]) == list(ASKED_TABLES)
    assert "pay-the-price" in ORACLES
    assert "pay-the-price" not in table["criteria"]


def test_every_question_fits_the_smallest_option_limit():
    for question in build_oracle_request(castle_state())["questions"].values():
        assert 2 <= len(question["criteria"]) <= MAX_OPTIONS


def test_questions_point_at_state_fields():
    request = build_oracle_request(castle_state())
    for question in request["questions"].values():
        fields = re.findall(r"`(\w+)`", question["instructions"])
        assert fields
        assert set(fields) <= set(request["state"])
        assert question["instructions"].count("?") == 1


def _answer(question: dict[str, Any], choice: str, top: float) -> dict[str, Any]:
    options = list(question["criteria"])
    rest = (1 - top) / (len(options) - 1)
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": {option: top if option == choice else rest for option in options},
        "confidence": 0.5,
    }


def _response(answers: dict[str, Any], ok: bool = True) -> dict[str, Any]:
    request = build_oracle_request(castle_state())
    questions = request["questions"]
    return {
        "request": request,
        "results": [
            {
                "target": "decision-1@foundry",
                "ok": ok,
                "latency_ms": 420.0,
                "warnings": [],
                "error": None if ok else {"code": "timeout", "message": "too slow"},
                "answers": {
                    question: _answer(questions[question], choice, top)
                    for question, (choice, top) in answers.items()
                },
            }
        ],
    }


def test_parse_reads_each_answer():
    response = _response(
        {
            KIND_QUESTION: (YES_NO, 0.9),
            LIKELIHOOD_QUESTION: ("likely", 0.6),
            TABLE_QUESTION: ("location", 0.3),
        }
    )
    decision = parse_oracle_decision(response, "decision-1@foundry")
    assert decision.ok
    assert decision.kind is not None and decision.kind.choice == YES_NO
    assert decision.likelihood is not None and decision.likelihood.choice == "likely"
    assert decision.table is not None and decision.table.choice == "location"
    assert decision.response is response


def test_a_failed_target_has_no_usable_answer():
    response = _response({}, ok=False)
    decision = parse_oracle_decision(response, "decision-1@foundry")
    assert not decision.ok
    assert decision.kind is None
    assert decision.error == "timeout: too slow"


def test_a_kind_answer_with_an_unknown_option_is_not_usable():
    response = _response({KIND_QUESTION: (YES_NO, 0.9)})
    response["results"][0]["answers"][KIND_QUESTION]["choice"] = "maybe"
    decision = parse_oracle_decision(response, "decision-1@foundry")
    assert not decision.ok
    assert decision.error is not None and "no usable kind answer" in decision.error


def test_parse_rejects_a_target_not_in_the_response():
    with pytest.raises(DecideError, match="no result for clef"):
        parse_oracle_decision(_response({}), "clef")
