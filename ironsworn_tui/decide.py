"""Builds decision requests, sends them to jevtester, and parses the answers."""

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ironsworn_tui.criteria import CriteriaStyle, move_criteria
from ironsworn_tui.moves import (
    ATTACK,
    CANNOT_TELL,
    Context,
    Initiative,
    stat_choices,
    stat_question_id,
    stat_question_options,
)
from ironsworn_tui.rules.datasworn import Datasworn
from ironsworn_tui.settings import Settings

MOVE_QUESTION = "move"
MOVE_INSTRUCTIONS = "Which move does the player's action trigger?"
STAT_CANNOT_TELL = "The action doesn't show which approach the character takes"
REQUEST_TIMEOUT_S = 60.0

type JsonObject = dict[str, Any]


class DecideError(Exception):
    """jevtester couldn't be reached, or it rejected the request."""


@dataclass(frozen=True)
class TurnState:
    """What the decision model knows about the turn.

    Attributes:
        character: The character's name and a few words about them.
        situation: The scene, as the player last described it with `/scene`, plus any active
            foes and journey.
        context: The context, which decides the `move` options.
        initiative: Who has initiative in a fight, or None outside one.
        player_says: What the player typed.
    """

    character: str
    situation: str
    context: Context
    initiative: Initiative | None
    player_says: str

    def to_json(self) -> JsonObject:
        """Return the state as the JSON object sent to the model."""
        return {
            "character": self.character,
            "situation": self.situation,
            "context": self.context.value,
            "initiative": self.initiative,
            "player_says": self.player_says,
        }


def _stat_instructions(data: Datasworn, option: str) -> str:
    if option == ATTACK:
        return "How does the character attack?"
    return f"Which approach does the character take for {data.move(option).name}?"


def build_request(data: Datasworn, state: TurnState, style: CriteriaStyle) -> JsonObject:
    """Build the decide request for a turn: the `move` question and every stat question.

    The move isn't known until the answers come back, so the request has a stat question for
    each move in the context that has one. The caller reads the one for the move the player
    confirms.

    Args:
        data: The Datasworn data.
        state: The turn's state.
        style: How the `move` question describes each move.

    Returns:
        The request body, with `state` and `questions`.
    """
    questions: JsonObject = {
        MOVE_QUESTION: {
            "type": "choice",
            "instructions": MOVE_INSTRUCTIONS,
            "criteria": move_criteria(data, state.context, style),
        }
    }
    for option in stat_question_options(data, state.context):
        criteria = {choice.stat: choice.text for choice in stat_choices(data, option)}
        criteria[CANNOT_TELL] = STAT_CANNOT_TELL
        questions[stat_question_id(option)] = {
            "type": "choice",
            "instructions": _stat_instructions(data, option),
            "criteria": criteria,
        }
    return {"state": state.to_json(), "questions": questions}


class _Response(BaseModel):
    model_config = ConfigDict(frozen=True)


class ChoiceAnswer(_Response):
    """A choice question's answer.

    Attributes:
        choice: The most probable option.
        probabilities: Each option's probability, in the question's option order.
        confidence: jevtester's confidence, `(p_max - 1/n) / (1 - 1/n)` for `n` options.
    """

    choice: str
    probabilities: dict[str, float]
    confidence: float

    def ranked(self) -> list[tuple[str, float]]:
        """Return the options and their probabilities, most probable first."""
        return sorted(self.probabilities.items(), key=lambda item: item[1], reverse=True)


class _ResultError(_Response):
    code: str
    message: str


class _TargetResult(_Response):
    target: str
    ok: bool
    latency_ms: float | None
    error: _ResultError | None
    answers: dict[str, ChoiceAnswer]


class _DecideResponse(_Response):
    results: list[_TargetResult]


@dataclass(frozen=True)
class Decision:
    """One target's answers to a turn's questions.

    Attributes:
        target: The target that answered.
        ok: False when the request failed, so the app shows the full move list.
        latency_ms: How long the target took, or None when nothing was sent.
        error: The error code and message when the request failed.
        move: The `move` answer, or None when the request failed.
        stats: The stat answers, by `move` option.
        response: The whole decide response, which case logging saves.
    """

    target: str
    ok: bool
    latency_ms: float | None
    error: str | None
    move: ChoiceAnswer | None
    stats: Mapping[str, ChoiceAnswer]
    response: JsonObject = field(repr=False)

    def stat_for(self, option: str) -> ChoiceAnswer | None:
        """Return the stat answer for a `move` option, or None if it has no stat question."""
        return self.stats.get(option)


def parse_decision(response: JsonObject, target: str) -> Decision:
    """Parse a decide response into one target's answers.

    Args:
        response: The decide response, as `POST /api/decide` or `jevtester decide --format
            json` returns it.
        target: The target to read.

    Returns:
        The target's answers.

    Raises:
        DecideError: If the response is malformed or has no result for the target.
    """
    try:
        parsed = _DecideResponse.model_validate(response)
    except ValidationError as error:
        raise DecideError(f"jevtester's response doesn't parse: {error}") from error
    result = next((r for r in parsed.results if r.target == target), None)
    if result is None:
        raise DecideError(f"jevtester's response has no result for {target}")
    prefix = "stat_"
    return Decision(
        target=target,
        ok=result.ok,
        latency_ms=result.latency_ms,
        error=f"{result.error.code}: {result.error.message}" if result.error else None,
        move=result.answers.get(MOVE_QUESTION) if result.ok else None,
        stats={
            question.removeprefix(prefix): answer
            for question, answer in result.answers.items()
            if question.startswith(prefix)
        },
        response=response,
    )


class JevtesterClient:
    """Sends decide requests to a running `jevtester serve`."""

    def __init__(self, base_url: str, timeout_s: float = REQUEST_TIMEOUT_S) -> None:
        """Create a client.

        Args:
            base_url: The server's root, such as `http://127.0.0.1:8641`.
            timeout_s: Seconds to wait for an answer.
        """
        self.base_url = base_url
        self.timeout_s = timeout_s

    def decide(self, request: JsonObject, target: str) -> Decision:
        """Send a request to one target and parse its answers.

        Args:
            request: A body from [`build_request`][ironsworn_tui.decide.build_request].
            target: The target to send it to.

        Returns:
            The answers. A target that failed gives a decision with `ok` False.

        Raises:
            DecideError: If jevtester can't be reached or rejects the request.
        """
        body = json.dumps({**request, "targets": [target]}).encode()
        http_request = urllib.request.Request(
            f"{self.base_url}/api/decide",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_s) as reply:
                response: JsonObject = json.load(reply)
        except urllib.error.HTTPError as error:
            raise DecideError(_error_message(error)) from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise DecideError(f"jevtester isn't reachable at {self.base_url}: {error}") from error
        return parse_decision(response, target)


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        detail: JsonObject = json.load(error)["error"]
        return f"{detail['code']}: {detail['message']}"
    except ValueError, KeyError, TypeError:
        return f"jevtester returned HTTP {error.code}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def serve_command(settings: Settings, port: int) -> list[str]:
    """Return the command that starts `jevtester serve` with this repository's config."""
    return [
        "uv",
        "run",
        "--project",
        str(settings.jevtester_project),
        "jevtester",
        "--config",
        str(settings.jevtester_config),
        "serve",
        "--port",
        str(port),
    ]


@contextmanager
def jevtester_server(
    settings: Settings, startup_timeout_s: float = 30.0
) -> Generator[JevtesterClient]:
    """Start `jevtester serve` on a free port, and stop it on exit.

    A subprocess per call adds about 0.7 seconds, so the app starts one server and sends every
    request to it. The server's log goes to `.jevtester/serve.log` beside the jevtester config.

    Args:
        settings: The app's settings, for the jevtester checkout and config.
        startup_timeout_s: Seconds to wait for the server to answer.

    Yields:
        A client for the server.

    Raises:
        DecideError: If the server exits or doesn't answer in time.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    root = settings.jevtester_config.parent
    log_path = root / ".jevtester" / "serve.log"
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            serve_command(settings, port), stdout=log, stderr=subprocess.STDOUT, cwd=root
        )
    try:
        _wait_until_ready(process, base_url, startup_timeout_s, log_path)
        yield JevtesterClient(base_url)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _wait_until_ready(
    process: subprocess.Popen[bytes], base_url: str, timeout_s: float, log_path: Path
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log = log_path.read_text(errors="replace")[-2000:]
            raise DecideError(f"jevtester serve exited with {process.returncode}: {log}")
        try:
            with urllib.request.urlopen(f"{base_url}/api/targets", timeout=1):
                return
        except urllib.error.URLError, ConnectionError, TimeoutError:
            time.sleep(0.1)
    raise DecideError(f"jevtester serve didn't answer within {timeout_s} seconds")
