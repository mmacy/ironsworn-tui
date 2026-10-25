"""Saving answered turns as jevtester cases."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ironsworn_tui.cases import ABSTAINED, CORRECTED, build_case, case_id, play_suite_name
from ironsworn_tui.commands import run_command
from ironsworn_tui.decide import DecideError, Decision, JsonObject, parse_decision
from ironsworn_tui.moves import NO_MOVE, Context
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import Decider, MoveInputs, TurnError
from tests.support import engine

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "decide-exploring-ditch.json"


class Sink:
    """Collects the cases the engine saves."""

    def __init__(self) -> None:
        self.saved: list[tuple[str, JsonObject]] = []

    def add_case(self, suite: str, case: JsonObject) -> None:
        self.saved.append((suite, case))


class BrokenSink:
    def add_case(self, suite: str, case: JsonObject) -> None:
        raise DecideError("409: The suite already has a case")


def ditch_decision():
    return parse_decision(json.loads(FIXTURE.read_text()), "decision-1@foundry")


def test_case_id_is_a_slug_and_a_timestamp():
    moment = datetime(2026, 10, 24, 21, 30, 5, 123456, tzinfo=UTC)
    assert case_id("Kira Ironhand", moment) == "kira-ironhand-20261024T213005123456"


def test_play_suite_names():
    assert [play_suite_name(c) for c in Context] == ["play-exploring", "play-journey", "play-fight"]


def test_case_takes_the_state_the_model_saw_and_what_the_player_did():
    decision = ditch_decision()
    assert decision.move is not None
    case = build_case(datasworn(), decision, decision.move.choice, "shadow", "kira-1")
    assert case["state"] == decision.response["request"]["state"]
    assert case["expected"] == {
        "move": {"answer": "secure_an_advantage"},
        "stat_secure_an_advantage": {"answer": "shadow"},
    }
    assert case["expected_action"] == "secure_an_advantage"
    assert case["tags"] == []
    assert case["provenance"] == "human"


def test_overriding_the_model_tags_the_case_corrected():
    case = build_case(datasworn(), ditch_decision(), "face_danger", "edge", "kira-1")
    assert case["tags"] == [CORRECTED]


def test_moves_without_a_stat_question_expect_no_stat():
    case = build_case(datasworn(), ditch_decision(), "gather_information", "wits", "kira-1")
    assert case["expected"] == {"move": {"answer": "gather_information"}}
    no_move = build_case(datasworn(), ditch_decision(), NO_MOVE, None, "kira-2")
    assert no_move["expected"] == {"move": {"answer": NO_MOVE}}
    assert no_move["expected_action"] == NO_MOVE


def test_a_scripted_session_adds_cases_to_the_right_suites(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    sink = Sink()
    turn.cases = sink

    decider.answers.append(("face_danger", "edge", 0.95))
    turn.suggest("I edge along the ledge.")
    dice.load(6, 1, 1)
    turn.make_move("face_danger", stat="edge")
    turn.resolve()

    decider.answers.append(("secure_an_advantage", "wits", 0.6))
    turn.suggest("I jump the three raiders by the fire.")
    dice.load(6, 1, 1)
    foes = MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    turn.make_move("enter_the_fray", stat="shadow", inputs=foes)
    turn.resolve()

    decider.answers.append(("attack", "iron", 0.9))
    turn.suggest("I wipe my brow.")
    turn.no_move()

    decider.answers.append(("attack", "iron", 0.9))
    turn.suggest("Hmm.")
    turn.skip()

    assert [suite for suite, _ in sink.saved] == ["play-exploring", "play-exploring", "play-fight"]
    first, second, third = (case for _, case in sink.saved)
    assert first["expected"] == {
        "move": {"answer": "face_danger"},
        "stat_face_danger": {"answer": "edge"},
    }
    assert first["tags"] == []
    assert second["expected"] == {
        "move": {"answer": "enter_the_fray"},
        "stat_enter_the_fray": {"answer": "shadow"},
    }
    assert second["tags"] == [CORRECTED]
    assert third["expected"] == {"move": {"answer": NO_MOVE}}
    assert third["state"]["player_says"] == "I wipe my brow."


class Raises:
    def decide(self, request: JsonObject, target: str) -> Decision:
        raise DecideError("jevtester isn't reachable")


class Fails:
    def decide(self, request: JsonObject, target: str) -> Decision:
        response = json.loads((FIXTURE.parent / "decide-target-failed.json").read_text())
        return parse_decision(response, "clef-flash@ollama")


@pytest.mark.parametrize("decider", [None, Raises(), Fails()])
def test_failed_requests_are_not_saved(tmp_path: Path, decider: Decider | None):
    turn, dice, _ = engine(tmp_path)
    sink = Sink()
    turn.cases = sink
    turn.decider = decider
    turn.suggest("I look around.")
    dice.load(6, 1, 1)
    turn.make_move("gather_information")
    turn.resolve()
    turn.no_move()
    assert sink.saved == []
    assert turn.campaign.log[-1].text == "No move"


def test_a_case_that_cannot_be_saved_leaves_a_note(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    turn.cases = BrokenSink()
    decider.answers.append(("face_danger", "edge", 0.95))
    turn.suggest("I edge along the ledge.")
    dice.load(6, 1, 1)
    turn.make_move("face_danger", stat="edge")
    assert turn.campaign.log[-2].text.startswith("Case not saved")


def test_a_refused_move_saves_nothing_until_it_succeeds(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    sink = Sink()
    turn.cases = sink
    decider.answers.append(("face_danger", "edge", 0.95))
    turn.suggest("I edge along the ledge.")
    with pytest.raises(TurnError, match="stats"):
        turn.make_move("face_danger")
    assert sink.saved == []
    dice.load(6, 1, 1)
    turn.make_move("face_danger", stat="edge")
    assert [suite for suite, _ in sink.saved] == ["play-exploring"]


def test_attacks_are_labeled_as_the_attack_option(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    sink = Sink()
    turn.cases = sink
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    decider.answers.append(("attack", "iron", 0.95))
    turn.suggest("I swing my axe.")
    dice.load(6, 1, 1)
    card = turn.make_move("attack", stat="edge")
    assert card is not None
    assert card.move == "strike"
    suite, case = sink.saved[-1]
    assert suite == "play-fight"
    assert case["expected"] == {"move": {"answer": "attack"}, "stat_attack": {"answer": "edge"}}


def test_overriding_cannot_tell_is_tagged_abstained(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    sink = Sink()
    turn.cases = sink
    decider.answers.append(("cannot_tell", None, 0.8))
    turn.suggest("Hmm, the river.")
    dice.load(6, 1, 1)
    turn.make_move("face_danger", stat="edge")
    assert sink.saved[-1][1]["tags"] == [ABSTAINED]


def test_a_move_from_a_changed_context_is_not_saved(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    sink = Sink()
    turn.cases = sink
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    decider.answers.append(("attack", "iron", 0.95))
    turn.suggest("I've had enough of this.")
    turn.end_fight("fled")
    dice.load(6, 1, 1)
    turn.make_move("make_camp")
    assert sink.saved == []
    assert turn.campaign.log[-2].text.startswith("Case not saved")


def test_vow_commands_after_a_message_are_saved(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    sink = Sink()
    turn.cases = sink
    decider.answers.append(("swear_an_iron_vow", None, 0.95))
    turn.suggest("I swear on my father's knife to find my brother.")
    dice.load(6, 1, 1)
    run_command(turn, "/vow swear dangerous Find my brother")
    turn.resolve()
    decider.answers.append(("forsake_your_vow", None, 0.95))
    turn.suggest("I give up on finding him.")
    run_command(turn, "/vow forsake Find my brother")
    answers = [case["expected"]["move"]["answer"] for _, case in sink.saved]
    assert answers == ["swear_an_iron_vow", "forsake_your_vow"]
