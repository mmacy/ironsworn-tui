"""The recognizer phrasings and oracle questions, the suites made from them, and the policies."""

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from ironsworn_tui.decide import ACTS_QUESTION, MOVE_QUESTION, build_oracle_request, build_request
from ironsworn_tui.experiment import (
    ESCALATE,
    SUITES_DIR,
    VARIANTS,
    generated_files,
    load_oracle_phrasings,
    load_phrasings,
    oracle_question_set,
    oracle_state,
    oracle_suite,
    question_set,
    suite,
    turn_state,
)
from ironsworn_tui.moves import CANNOT_TELL, Context, context_options
from ironsworn_tui.oracles import ASKED_TABLES, LIKELIHOOD_OPTIONS
from ironsworn_tui.rules.datasworn import datasworn

PHRASINGS = load_phrasings()
ORACLE = load_oracle_phrasings()


def _generated() -> dict[Path, str]:
    return generated_files(datasworn(), PHRASINGS, ORACLE)


@pytest.mark.parametrize("context", list(Context))
def test_forty_phrasings_per_context(context: Context):
    assert len(PHRASINGS.for_context(context)) == 40


@pytest.mark.parametrize("context", list(Context))
def test_every_option_has_a_phrasing(context: Context):
    expected = Counter(phrasing.move for phrasing in PHRASINGS.for_context(context))
    assert set(expected) == set(context_options(context))


def test_the_guide_ambiguities_are_covered():
    tags = {tag for context in Context for p in PHRASINGS.for_context(context) for tag in p.tags}
    assert {"fd-vs-saa", "gi-vs-saa", "camp-vs-sojourn", "adversarial", "out-of-character"} <= tags


@pytest.mark.parametrize("context", list(Context))
def test_question_set_matches_what_play_sends(context: Context):
    phrasing = PHRASINGS.for_context(context)[0]
    state = turn_state(PHRASINGS, context, phrasing)
    for variant in VARIANTS:
        sent = build_request(datasworn(), state, variant.style, variant.shape)["questions"]
        assert question_set(datasworn(), context, variant)["questions"] == sent


def test_generated_files_are_up_to_date():
    for relative, text in _generated().items():
        path = SUITES_DIR / relative
        assert path.exists(), f"run `uv run ironsworn-tui write-suites` to create {relative}"
        assert path.read_text() == text, f"run `uv run ironsworn-tui write-suites`: {relative}"


def _load(path: Path) -> dict[str, Any]:
    loader: Any = YAML(typ="safe", pure=True)
    loaded: dict[str, Any] = loader.load(path)
    return loaded


@pytest.mark.parametrize("name", ["moves", "moves-acts"])
def test_policy_maps_every_option_to_itself(name: str):
    policy = _load(SUITES_DIR / "policies" / f"{name}.yaml")
    rules = {
        rule["when"]["move"]: rule["action"] for rule in policy["rules"] if "move" in rule["when"]
    }
    options = {option for context in Context for option in context_options(context)}
    assert set(rules) == options
    assert all(action == option for option, action in rules.items())
    assert policy["bands"]["move"] == {"act": "act", "confirm": "confirm"}
    assert policy["thresholds"] == {"act": 0.7, "confirm": 0.4}


def test_acts_policy_checks_acts_first():
    policy = _load(SUITES_DIR / "policies" / "moves-acts.yaml")
    assert policy["rules"][0] == {"action": "cannot_tell", "when": {ACTS_QUESTION: False}}


def test_the_user_approved_the_cases():
    for relative in _generated():
        if relative.parent == Path("."):
            cases = _load(SUITES_DIR / relative)["cases"]
            assert {case["provenance"] for case in cases} == {"human"}


def test_acts_suite_expects_no_move_answer_for_cannot_tell():
    acts = next(variant for variant in VARIANTS if variant.shape.acts_question)
    cases = suite(datasworn(), PHRASINGS, Context.EXPLORING, acts)["cases"]
    for case, phrasing in zip(cases, PHRASINGS.for_context(Context.EXPLORING), strict=True):
        assert case["expected"][ACTS_QUESTION] == {"answer": phrasing.move != CANNOT_TELL}
        assert (MOVE_QUESTION in case["expected"]) == (phrasing.move != CANNOT_TELL)


def test_no_stale_generated_files():
    generated = set(_generated())
    on_disk = {
        path.relative_to(SUITES_DIR)
        for pattern in ("recognizer-*.yaml", "question-sets/moves-*.yaml", "question-sets/oracle*")
        for path in SUITES_DIR.glob(pattern)
    }
    assert on_disk == generated


@pytest.mark.parametrize("context", list(Context))
def test_play_suites_ask_what_play_sends(context: Context):
    suite = _load(SUITES_DIR / f"play-{context.value}.yaml")
    assert suite["question_set"] == f"moves-{context.value}-guide"
    assert suite["policy"] == "moves"


def test_forty_to_sixty_oracle_questions():
    assert 40 <= len(ORACLE.questions) <= 60


def test_every_likelihood_and_table_has_an_oracle_question():
    likelihoods = {q.likelihood for q in ORACLE.questions if q.kind == "yes_no"}
    tables = {q.table for q in ORACLE.questions if q.kind == "table"}
    assert likelihoods == set(LIKELIHOOD_OPTIONS)
    assert set(ASKED_TABLES) <= tables
    assert {q.kind for q in ORACLE.questions} == {"yes_no", "table", "cannot_tell"}
    assert any(q.also_kind for q in ORACLE.questions)


def test_oracle_question_set_matches_what_play_sends():
    state = oracle_state(ORACLE, ORACLE.questions[0])
    assert oracle_question_set()["questions"] == build_oracle_request(state)["questions"]


def test_oracle_cases_expect_the_answer_the_kind_calls_for():
    cases = oracle_suite(ORACLE)["cases"]
    for case, question in zip(cases, ORACLE.questions, strict=True):
        assert case["expected"]["kind"]["answer"] == question.kind
        if question.kind == "yes_no":
            assert case["expected_action"] == question.likelihood
        elif question.kind == "table" and question.table is not None:
            assert case["expected_action"] == question.table
        else:
            assert case["expected_action"] == ESCALATE


def test_oracle_policy_maps_every_option_to_itself():
    policy = _load(SUITES_DIR / "policies" / "oracle.yaml")
    rules = policy["rules"]
    assert rules[0] == {"action": ESCALATE, "when": {"kind": CANNOT_TELL}}
    likelihoods = {r["when"]["likelihood"]: r["action"] for r in rules if "likelihood" in r["when"]}
    tables = {r["when"]["table"]: r["action"] for r in rules if "table" in r["when"]}
    assert likelihoods == {option: option for option in LIKELIHOOD_OPTIONS}
    assert tables == {table: table for table in ASKED_TABLES}
    assert policy["bands"] == {"kind": {"act": "act", "confirm": "act"}}
    assert policy["default"] == ESCALATE


def test_play_oracle_suite_asks_what_play_sends():
    suite = _load(SUITES_DIR / "play-oracle.yaml")
    assert suite["question_set"] == "oracle"
    assert suite["policy"] == "oracle"
