"""Building decision requests and parsing jevtester's answers, against recorded responses."""

import copy
import dataclasses
import json
import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import (
    MOVE_QUESTION,
    TARGET_TIMEOUT_S,
    DecideError,
    JevtesterClient,
    TurnState,
    build_request,
    parse_decision,
)
from ironsworn_tui.moves import ATTACK, CANNOT_TELL, Context, Initiative, context_options
from ironsworn_tui.rules.datasworn import datasworn

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return loaded


def ditch_state(context: Context = Context.EXPLORING) -> TurnState:
    return TurnState(
        name="Kira",
        character="Kira, a hunter",
        situation="Pinned behind a cart. Two raiders with bows hold the ridge above the road.",
        context=context,
        initiative="foe" if context is Context.FIGHT else None,
        player_says="I creep along the ditch to get behind the ridge where they can't see me.",
    )


def test_state_matches_the_plan():
    assert ditch_state().to_json() == {
        "character": "Kira, a hunter",
        "circumstances": "Kira is exploring, and no fight or journey is under way.",
        "situation": "Pinned behind a cart. Two raiders with bows hold the ridge above the road.",
        "player_says": "I creep along the ditch to get behind the ridge where they can't see me.",
    }


@pytest.mark.parametrize(
    ("context", "initiative", "expected"),
    [
        (Context.JOURNEY, None, "Kira is on a journey, and no fight is under way."),
        (Context.FIGHT, "character", "Kira is in a fight and has initiative."),
        (Context.FIGHT, "foe", "Kira is in a fight, and the foe has initiative."),
    ],
)
def test_circumstances(context: Context, initiative: Initiative | None, expected: str):
    state = dataclasses.replace(ditch_state(), context=context, initiative=initiative)
    assert state.circumstances == expected


@pytest.mark.parametrize(
    ("context", "initiative"),
    [(Context.FIGHT, None), (Context.EXPLORING, "character"), (Context.JOURNEY, "foe")],
)
def test_initiative_must_match_the_context(context: Context, initiative: Initiative | None):
    with pytest.raises(ValueError, match="initiative"):
        dataclasses.replace(ditch_state(), context=context, initiative=initiative)


def test_questions_point_at_state_fields():
    request = build_request(datasworn(), ditch_state(), CriteriaStyle.GUIDE)
    fields = set(request["state"])
    for question in request["questions"].values():
        named = set(re.findall(r"`([a-z_]+)`", question["instructions"]))
        assert named, question["instructions"]
        assert named <= fields


@pytest.mark.parametrize("context", list(Context))
def test_questions_do_not_name_a_move(context: Context):
    request = build_request(datasworn(), ditch_state(context), CriteriaStyle.GUIDE)
    names = [move.name.lower() for move in datasworn().moves.values()]
    for question in request["questions"].values():
        instructions = question["instructions"].lower()
        assert not any(name in instructions for name in names)
        assert "attack" not in instructions


def test_fixture_request_matches_the_current_request():
    recorded = load_fixture("decide-exploring-ditch.json")["request"]
    current = build_request(datasworn(), ditch_state(), CriteriaStyle.GUIDE)
    assert recorded["state"] == current["state"]
    assert recorded["questions"] == current["questions"]


@pytest.mark.parametrize("context", list(Context))
def test_request_has_a_move_question_with_the_context_options(context: Context):
    request = build_request(datasworn(), ditch_state(context), CriteriaStyle.GUIDE)
    move = request["questions"][MOVE_QUESTION]
    assert move["type"] == "choice"
    assert tuple(move["criteria"]) == context_options(context)


def test_exploring_request_has_a_stat_question_per_stat_move():
    request = build_request(datasworn(), ditch_state(), CriteriaStyle.GUIDE)
    assert list(request["questions"]) == [
        "move",
        "stat_face_danger",
        "stat_secure_an_advantage",
        "stat_compel",
        "stat_enter_the_fray",
    ]


def test_stat_question_offers_each_approach_and_cannot_tell():
    request = build_request(datasworn(), ditch_state(), CriteriaStyle.GUIDE)
    stat = request["questions"]["stat_face_danger"]
    assert stat["type"] == "choice"
    assert list(stat["criteria"]) == ["edge", "heart", "iron", "shadow", "wits", CANNOT_TELL]
    assert stat["criteria"]["shadow"] == "With deception, stealth, or trickery"


def test_fight_request_asks_how_the_character_attacks():
    request = build_request(datasworn(), ditch_state(Context.FIGHT), CriteriaStyle.GUIDE)
    attack = request["questions"][f"stat_{ATTACK}"]
    assert list(attack["criteria"]) == ["iron", "edge", CANNOT_TELL]


def test_request_body_names_no_targets():
    request = build_request(datasworn(), ditch_state(), CriteriaStyle.GUIDE)
    assert set(request) == {"state", "questions"}


def test_request_uses_the_criteria_style():
    guide = build_request(datasworn(), ditch_state(), CriteriaStyle.GUIDE)
    trigger = build_request(datasworn(), ditch_state(), CriteriaStyle.TRIGGER)
    guide_text = guide["questions"]["move"]["criteria"]["face_danger"]
    trigger_text = trigger["questions"]["move"]["criteria"]["face_danger"]
    assert trigger_text.startswith("When you")
    assert guide_text != trigger_text


def test_parse_recorded_answer():
    decision = parse_decision(load_fixture("decide-exploring-ditch.json"), "decision-1@foundry")
    assert decision.ok is True
    assert decision.error is None
    assert decision.move is not None
    assert decision.move.choice in context_options(Context.EXPLORING)
    assert set(decision.move.probabilities) == set(context_options(Context.EXPLORING))
    assert 0.0 <= decision.move.confidence <= 1.0
    assert decision.latency_ms is not None


def test_parse_recorded_stat_answers():
    decision = parse_decision(load_fixture("decide-exploring-ditch.json"), "decision-1@foundry")
    face_danger = decision.stat_for("face_danger")
    assert face_danger is not None
    assert face_danger.choice in {"edge", "heart", "iron", "shadow", "wits", CANNOT_TELL}
    assert decision.stat_for("heal") is None


def test_ranked_moves_are_most_probable_first():
    decision = parse_decision(load_fixture("decide-exploring-ditch.json"), "decision-1@foundry")
    assert decision.move is not None
    ranked = decision.move.ranked()
    assert ranked[0][0] == decision.move.choice
    probabilities = [probability for _, probability in ranked]
    assert probabilities == sorted(probabilities, reverse=True)


def test_parse_recorded_failure():
    decision = parse_decision(load_fixture("decide-target-failed.json"), "clef-flash@ollama")
    assert decision.ok is False
    assert decision.move is None
    assert decision.error is not None
    assert decision.error.startswith("bad_request")


def _with_move_answer(answer: dict[str, Any] | None) -> dict[str, Any]:
    """The recorded response, with its `move` answer replaced or removed."""
    response = copy.deepcopy(load_fixture("decide-exploring-ditch.json"))
    answers = response["results"][0]["answers"]
    if answer is None:
        del answers["move"]
        response["results"][0]["warnings"] = [
            {"code": "missing_answer", "message": "No answer for move", "question": "move"}
        ]
    else:
        answers["move"] = answer
    return response


def test_ok_result_without_a_move_answer_is_not_usable():
    decision = parse_decision(_with_move_answer(None), "decision-1@foundry")
    assert decision.ok is False
    assert decision.move is None
    assert decision.error is not None
    assert "missing_answer" in decision.error
    assert decision.warnings == ("missing_answer: No answer for move",)
    assert decision.stat_for("face_danger") is not None


def test_move_answer_with_an_unknown_option_is_not_usable():
    answer = {
        "type": "choice",
        "choice": "dance",
        "probabilities": {},
        "unknown_probabilities": {"dance": 0.9},
        "confidence": 0.8,
        "server_confidence": None,
    }
    decision = parse_decision(_with_move_answer(answer), "decision-1@foundry")
    assert decision.ok is False
    assert decision.move is None


def test_noul_answers_parse():
    response = copy.deepcopy(load_fixture("decide-exploring-ditch.json"))
    response["request"]["questions"]["acts"] = {"type": "noul", "instructions": "Acts?"}
    response["results"][0]["answers"]["acts"] = {
        "type": "noul",
        "probability": 0.97,
        "confidence": 0.94,
        "server_confidence": None,
    }
    decision = parse_decision(response, "decision-1@foundry")
    assert decision.ok is True
    assert "acts" not in decision.stats


def test_parse_keeps_the_whole_response_for_case_logging():
    response = load_fixture("decide-exploring-ditch.json")
    decision = parse_decision(response, "decision-1@foundry")
    assert decision.response == response


def test_parse_rejects_a_target_not_in_the_response():
    with pytest.raises(DecideError):
        parse_decision(load_fixture("decide-exploring-ditch.json"), "clef-flash@workers-ai")


class _StubHandler(BaseHTTPRequestHandler):
    response: ClassVar[tuple[int, dict[str, Any] | bytes]] = (200, {})
    received: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        type(self).received.append(json.loads(self.rfile.read(length)))
        status, body = type(self).response
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def stub_server() -> Iterator[str]:
    _StubHandler.received.clear()
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_client_posts_the_request_with_the_target(stub_server: str):
    _StubHandler.response = (200, load_fixture("decide-exploring-ditch.json"))
    client = JevtesterClient(stub_server)
    request = build_request(datasworn(), ditch_state(), CriteriaStyle.GUIDE)
    decision = client.decide(request, "decision-1@foundry")
    assert decision.ok is True
    sent = _StubHandler.received[0]
    assert sent["targets"] == ["decision-1@foundry"]
    assert sent["questions"] == request["questions"]
    assert sent["timeout_s"] == TARGET_TIMEOUT_S
    assert client.timeout_s > TARGET_TIMEOUT_S


def test_client_raises_on_a_reply_that_is_not_json(stub_server: str):
    _StubHandler.response = (200, b"<html>not json</html>")
    with pytest.raises(DecideError, match="JSON"):
        JevtesterClient(stub_server).decide({"state": "x", "questions": {}}, "decision-1@foundry")


def test_client_reports_an_error_body_that_is_not_json(stub_server: str):
    _StubHandler.response = (502, b"Bad gateway")
    with pytest.raises(DecideError, match="HTTP 502"):
        JevtesterClient(stub_server).decide({"state": "x", "questions": {}}, "decision-1@foundry")


def test_client_raises_on_an_invalid_request(stub_server: str):
    _StubHandler.response = (
        422,
        {"error": {"code": "invalid_request", "message": "bad", "field": "questions"}},
    )
    client = JevtesterClient(stub_server)
    with pytest.raises(DecideError, match="invalid_request"):
        client.decide({"state": "x", "questions": {}}, "decision-1@foundry")


def test_client_raises_when_jevtester_is_not_running():
    client = JevtesterClient("http://127.0.0.1:9")
    with pytest.raises(DecideError):
        client.decide({"state": "x", "questions": {}}, "decision-1@foundry")
