"""The recognizer phrasings, the suites made from them, and the moves policy."""

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import build_request
from ironsworn_tui.experiment import (
    SUITES_DIR,
    generated_files,
    load_phrasings,
    question_set,
    turn_state,
)
from ironsworn_tui.moves import Context, context_options
from ironsworn_tui.rules.datasworn import datasworn

PHRASINGS = load_phrasings()


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
    for style in CriteriaStyle:
        sent = build_request(datasworn(), state, style)["questions"]
        assert question_set(datasworn(), context, style)["questions"] == sent


def test_generated_files_are_up_to_date():
    for relative, text in generated_files(datasworn(), PHRASINGS).items():
        path = SUITES_DIR / relative
        assert path.exists(), f"run `uv run ironsworn-tui write-suites` to create {relative}"
        assert path.read_text() == text, f"run `uv run ironsworn-tui write-suites`: {relative}"


def _load(path: Path) -> dict[str, Any]:
    loader: Any = YAML(typ="safe", pure=True)
    loaded: dict[str, Any] = loader.load(path)
    return loaded


def test_policy_maps_every_option_to_itself():
    policy = _load(SUITES_DIR / "policies" / "moves.yaml")
    rules = {rule["when"]["move"]: rule["action"] for rule in policy["rules"]}
    options = {option for context in Context for option in context_options(context)}
    assert set(rules) == options
    assert all(action == option for option, action in rules.items())
    assert policy["bands"]["move"] == {"act": "act", "confirm": "confirm"}
    assert policy["thresholds"] == {"act": 0.7, "confirm": 0.4}


def test_suites_mark_cases_as_drafts_until_a_person_approves_them():
    for relative in generated_files(datasworn(), PHRASINGS):
        if relative.parent == Path("."):
            cases = _load(SUITES_DIR / relative)["cases"]
            assert {case["provenance"] for case in cases} == {"claude-draft"}
