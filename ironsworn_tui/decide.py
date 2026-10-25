"""Builds decision requests, sends them to jevtester, and parses the answers."""

import http.client
import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ironsworn_tui.criteria import CriteriaStyle, move_criteria
from ironsworn_tui.moves import (
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
MOVE_INSTRUCTIONS = (
    "Which move does the action in `player_says` trigger, given `circumstances` and `situation`?"
)
STAT_INSTRUCTIONS = "How does the character go about the action in `player_says`?"
STAT_CANNOT_TELL = "The player names the action but not the manner of doing it"
# jevtester gives up on the target after this long and returns a result with `ok` False. The
# client waits longer, so that result arrives instead of a socket timeout.
TARGET_TIMEOUT_S = 30.0
CLIENT_TIMEOUT_S = TARGET_TIMEOUT_S + 15.0
SERVER_STARTS = 3

type JsonObject = dict[str, Any]


class DecideError(Exception):
    """jevtester couldn't be reached, or it rejected the request."""


@dataclass(frozen=True)
class TurnState:
    """What the app knows about the turn, and the part of it the decision model sees.

    Attributes:
        name: The character's name, such as "Kira".
        character: The character's name and a few words about them, such as "Kira, a hunter".
        situation: The scene, as the player last described it with `/scene`.
        context: The context, which decides the `move` options. The model sees it as a sentence
            in `circumstances`.
        initiative: Who has initiative in a fight, or None outside one.
        player_says: What the player typed.
    """

    name: str
    character: str
    situation: str
    context: Context
    initiative: Initiative | None
    player_says: str

    def __post_init__(self) -> None:
        """Check that initiative is set exactly when there's a fight.

        Raises:
            ValueError: If initiative and the context disagree.
        """
        if (self.initiative is None) == (self.context is Context.FIGHT):
            raise ValueError(f"initiative {self.initiative} doesn't fit context {self.context}")

    @property
    def circumstances(self) -> str:
        """The context and initiative as a sentence, such as "Kira is exploring"."""
        match self.context, self.initiative:
            case Context.FIGHT, "character":
                return f"{self.name} is in a fight and has initiative."
            case Context.FIGHT, _:
                return f"{self.name} is in a fight, and the foe has initiative."
            case Context.JOURNEY, _:
                return f"{self.name} is on a journey, and no fight is under way."
            case _:
                return f"{self.name} is exploring, and no fight or journey is under way."

    def to_json(self) -> JsonObject:
        """Return the state the model sees.

        Decision models read the field names, and do better with sentences than with coded
        values, so the context and initiative go in as the `circumstances` sentence.
        """
        return {
            "character": self.character,
            "circumstances": self.circumstances,
            "situation": self.situation,
            "player_says": self.player_says,
        }


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
            "instructions": STAT_INSTRUCTIONS,
            "criteria": criteria,
        }
    return {"state": state.to_json(), "questions": questions}


class _Response(BaseModel):
    model_config = ConfigDict(frozen=True)


class ChoiceAnswer(_Response):
    """A choice question's answer.

    Attributes:
        choice: The option the server chose, normally the most probable one.
        probabilities: The probability of each option the server sent, in option order.
        confidence: jevtester's confidence, `(p_max - 1/n) / (1 - 1/n)` for `n` options.
    """

    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float]
    confidence: float

    def ranked(self) -> list[tuple[str, float]]:
        """Return the options and their probabilities, most probable first."""
        return sorted(self.probabilities.items(), key=lambda item: item[1], reverse=True)


class NoulAnswer(_Response):
    """A yes/no question's answer.

    Attributes:
        probability: The probability of yes.
    """

    type: Literal["noul"]
    probability: float


class ScoreAnswer(_Response):
    """A score question's answer.

    Attributes:
        level: The most probable level, from 0.
    """

    type: Literal["score"]
    level: int


type Answer = Annotated[ChoiceAnswer | NoulAnswer | ScoreAnswer, Field(discriminator="type")]


class _ResultError(_Response):
    code: str
    message: str


class _ResultWarning(_Response):
    code: str
    message: str


class _TargetResult(_Response):
    target: str
    ok: bool
    latency_ms: float | None
    warnings: list[_ResultWarning]
    error: _ResultError | None
    answers: dict[str, Answer]


class _ChoiceQuestion(_Response):
    type: Literal["choice"]
    criteria: dict[str, str]


class _OtherQuestion(_Response):
    type: Literal["noul", "score"]


class _Request(_Response):
    questions: dict[str, Annotated[_ChoiceQuestion | _OtherQuestion, Field(discriminator="type")]]


class _DecideResponse(_Response):
    request: _Request
    results: list[_TargetResult]


@dataclass(frozen=True)
class Decision:
    """One target's answers to a turn's questions.

    Attributes:
        target: The target that answered.
        ok: True when there's a usable `move` answer. When it's False, the app shows the full
            move list.
        latency_ms: How long the target took, or None when nothing was sent.
        error: Why there's no usable `move` answer, when `ok` is False.
        move: The `move` answer, or None when `ok` is False.
        stats: The usable stat answers, by `move` option.
        warnings: jevtester's warnings, as `code: message`.
        response: The whole decide response, which case logging saves.
    """

    target: str
    ok: bool
    latency_ms: float | None
    error: str | None
    move: ChoiceAnswer | None
    stats: Mapping[str, ChoiceAnswer]
    warnings: tuple[str, ...]
    response: JsonObject = field(repr=False)

    def stat_for(self, option: str) -> ChoiceAnswer | None:
        """Return the stat answer for a `move` option, or None if it has no usable one."""
        return self.stats.get(option)


def _usable_choice(
    parsed: _DecideResponse, answers: dict[str, Answer], question: str
) -> ChoiceAnswer | None:
    """Return a choice answer when it names one of its question's options."""
    answer = answers.get(question)
    asked = parsed.request.questions.get(question)
    if not isinstance(answer, ChoiceAnswer) or not isinstance(asked, _ChoiceQuestion):
        return None
    return answer if answer.choice in asked.criteria else None


def parse_decision(response: JsonObject, target: str) -> Decision:
    """Parse a decide response into one target's answers.

    A result can be `ok` in jevtester's terms and still lack a usable `move` answer, when the
    model left it out or chose an option the question doesn't have. Both give a decision with
    `ok` False. A stat answer with an unknown option is left out of `stats`.

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
    warnings = tuple(f"{w.code}: {w.message}" for w in result.warnings)
    move = _usable_choice(parsed, result.answers, MOVE_QUESTION) if result.ok else None
    problem: str | None = None
    if result.error is not None:
        problem = f"{result.error.code}: {result.error.message}"
    elif move is None:
        problem = "no usable move answer" + (f" ({'; '.join(warnings)})" if warnings else "")
    prefix = "stat_"
    stats: dict[str, ChoiceAnswer] = {}
    for question in result.answers:
        stat = _usable_choice(parsed, result.answers, question)
        if question.startswith(prefix) and stat is not None:
            stats[question.removeprefix(prefix)] = stat
    return Decision(
        target=target,
        ok=move is not None,
        latency_ms=result.latency_ms,
        error=problem,
        move=move,
        stats=stats,
        warnings=warnings,
        response=response,
    )


# The app talks to a server on 127.0.0.1, so it never goes through a proxy.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class JevtesterClient:
    """Sends decide requests to a running `jevtester serve`."""

    def __init__(self, base_url: str, timeout_s: float = CLIENT_TIMEOUT_S) -> None:
        """Create a client.

        Args:
            base_url: The server's root, such as `http://127.0.0.1:8641`.
            timeout_s: Seconds to wait for an answer. It must be longer than
                `TARGET_TIMEOUT_S`, which the request asks jevtester to wait for the target.
        """
        self.base_url = base_url
        self.timeout_s = timeout_s

    def decide(self, request: JsonObject, target: str) -> Decision:
        """Send a request to one target and parse its answers.

        Args:
            request: A body from [`build_request`][ironsworn_tui.decide.build_request].
            target: The target to send it to.

        Returns:
            The answers. A target that failed or timed out gives a decision with `ok` False.

        Raises:
            DecideError: If jevtester can't be reached, rejects the request, or sends a reply
                that doesn't parse.
        """
        body = {**request, "targets": [target], "timeout_s": TARGET_TIMEOUT_S}
        http_request = urllib.request.Request(
            f"{self.base_url}/api/decide",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _OPENER.open(http_request, timeout=self.timeout_s) as reply:
                response: JsonObject = json.load(reply)
        except urllib.error.HTTPError as error:
            raise DecideError(_error_message(error)) from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise DecideError(f"jevtester isn't reachable at {self.base_url}: {error}") from error
        except (ValueError, http.client.HTTPException) as error:
            raise DecideError(f"jevtester's reply isn't valid JSON: {error}") from error
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
    request to it. The server runs in its own process group, so stopping it also stops the
    jevtester process that `uv run` starts. Its log goes to `.jevtester/serve.log` beside the
    jevtester config. If the port is taken before the server binds it, startup tries another.

    Args:
        settings: The app's settings, for the jevtester checkout and config.
        startup_timeout_s: Seconds to wait for the server to answer, on each try.

    Yields:
        A client for the server.

    Raises:
        DecideError: If the server can't be started or doesn't answer in time.
    """
    root = settings.jevtester_config.parent
    log_path = root / ".jevtester" / "serve.log"
    log_path.parent.mkdir(exist_ok=True)
    last_error = DecideError("jevtester serve wasn't started")
    for _ in range(SERVER_STARTS):
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = _start(serve_command(settings, port), root, log_path)
        try:
            _wait_until_ready(process, base_url, startup_timeout_s, log_path)
        except DecideError as error:
            _stop(process)
            last_error = error
            continue
        try:
            yield JevtesterClient(base_url)
        finally:
            _stop(process)
        return
    raise last_error


def _start(command: list[str], root: Path, log_path: Path) -> subprocess.Popen[bytes]:
    try:
        with log_path.open("ab") as log:
            return subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=root,
                start_new_session=True,
            )
    except OSError as error:
        raise DecideError(f"can't start jevtester serve: {error}") from error


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Stop the server's whole process group: politely, then by force after 5 seconds."""
    for sig, wait_s in ((signal.SIGTERM, 5.0), (signal.SIGKILL, None)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        try:
            process.wait(timeout=wait_s)
            break
        except subprocess.TimeoutExpired:
            continue


def _wait_until_ready(
    process: subprocess.Popen[bytes], base_url: str, timeout_s: float, log_path: Path
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log = log_path.read_text(errors="replace")[-2000:]
            raise DecideError(f"jevtester serve exited with {process.returncode}: {log}")
        try:
            with _OPENER.open(f"{base_url}/api/targets", timeout=1) as reply:
                targets: JsonObject = json.load(reply)
        except urllib.error.URLError, ConnectionError, TimeoutError, ValueError:
            time.sleep(0.1)
            continue
        # Another server could answer on a port taken in a race, so check that this one
        # is jevtester and that the process started here is still running.
        if "targets" in targets and process.poll() is None:
            return
    raise DecideError(f"jevtester serve didn't answer within {timeout_s} seconds")
