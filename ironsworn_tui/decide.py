"""Builds decision requests, sends them to jevtester, and parses the answers.

There are two requests: the turn's, which asks which move a message triggers, and the oracle's,
which asks how to answer a question typed after `/oracle`.
"""

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

from ironsworn_tui.criteria import (
    ORACLE_KIND_CRITERIA,
    CriteriaStyle,
    likelihood_criteria,
    move_criteria,
    table_criteria,
)
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
ACTS_QUESTION = "acts"
ACTS_INSTRUCTIONS = "Does `player_says` describe something the character does?"
STAT_CANNOT_TELL = "The player names the action but not the manner of doing it"
KIND_QUESTION = "kind"
KIND_INSTRUCTIONS = "What kind of answer does `question` ask for?"
LIKELIHOOD_QUESTION = "likelihood"
LIKELIHOOD_INSTRUCTIONS = "How likely is a yes to `question`, given `character` and `situation`?"
TABLE_QUESTION = "table"
TABLE_INSTRUCTIONS = "Which oracle table gives the answer that `question` asks for?"
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
        name: The character's name, such as "Blarg".
        character: The character's name and a few words about them, such as "Blarg, the Destructor".
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
        """The context and initiative as a sentence, such as "Blarg is exploring"."""
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


@dataclass(frozen=True)
class RequestShape:
    """How a request handles messages that don't fit an option, for the recognizer experiment.

    The defaults are what play sends. In the experiment, a `cannot_tell` option on the stat
    questions won 12 of 14 stat misses, and stat accuracy is higher on both targets without it.
    The `acts` question lowered move accuracy on both. `experiments/results.md` has the numbers.

    Attributes:
        stat_abstain: True to give each stat question a `cannot_tell` option.
        acts_question: True to replace the `move` question's `cannot_tell` option with a
            yes/no question, `acts`, asking whether the player describes an action at all.
            TypeSafe recommends this companion question over an abstain option.
    """

    stat_abstain: bool = False
    acts_question: bool = False


DEFAULT_SHAPE = RequestShape()


def build_request(
    data: Datasworn, state: TurnState, style: CriteriaStyle, shape: RequestShape = DEFAULT_SHAPE
) -> JsonObject:
    """Build the decide request for a turn: the `move` question and every stat question.

    The move isn't known until the answers come back, so the request has a stat question for
    each move in the context that has one. The caller reads the one for the move the player
    confirms.

    Args:
        data: The Datasworn data.
        state: The turn's state.
        style: How the `move` question describes each move.
        shape: How the request handles messages that don't fit an option.

    Returns:
        The request body, with `state` and `questions`.
    """
    move = move_criteria(data, state.context, style)
    if shape.acts_question:
        del move[CANNOT_TELL]
    questions: JsonObject = {
        MOVE_QUESTION: {"type": "choice", "instructions": MOVE_INSTRUCTIONS, "criteria": move}
    }
    if shape.acts_question:
        questions[ACTS_QUESTION] = {"type": "noul", "instructions": ACTS_INSTRUCTIONS}
    for option in stat_question_options(data, state.context):
        criteria = {choice.stat: choice.text for choice in stat_choices(data, option)}
        if shape.stat_abstain:
            criteria[CANNOT_TELL] = STAT_CANNOT_TELL
        questions[stat_question_id(option)] = {
            "type": "choice",
            "instructions": STAT_INSTRUCTIONS,
            "criteria": criteria,
        }
    return {"state": state.to_json(), "questions": questions}


@dataclass(frozen=True)
class OracleState:
    """The state the decision model sees for a question typed after `/oracle`.

    Attributes:
        character: The character's name and a few words about them.
        situation: The scene, as the player last described it with `/scene`.
        question: The question the player typed.
    """

    character: str
    situation: str
    question: str

    def to_json(self) -> JsonObject:
        """Return the state the model sees."""
        return {"character": self.character, "situation": self.situation, "question": self.question}


def build_oracle_request(state: OracleState) -> JsonObject:
    """Build the decide request for an oracle question.

    It asks three questions in one request: `kind`, whether a yes or no answers the question
    or a table does; `likelihood`, how likely a yes is; and `table`, which table gives the
    answer. The caller reads `likelihood` or `table`, as the `kind` answer says.

    Args:
        state: The question and what it depends on.

    Returns:
        The request body, with `state` and `questions`.
    """
    questions: JsonObject = {
        KIND_QUESTION: {
            "type": "choice",
            "instructions": KIND_INSTRUCTIONS,
            "criteria": dict(ORACLE_KIND_CRITERIA),
        },
        LIKELIHOOD_QUESTION: {
            "type": "choice",
            "instructions": LIKELIHOOD_INSTRUCTIONS,
            "criteria": likelihood_criteria(),
        },
        TABLE_QUESTION: {
            "type": "choice",
            "instructions": TABLE_INSTRUCTIONS,
            "criteria": table_criteria(),
        },
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
        acts: The probability that the player describes an action, when the request asked.
        warnings: jevtester's warnings, as `code: message`.
        response: The whole decide response, which case logging saves.
    """

    target: str
    ok: bool
    latency_ms: float | None
    error: str | None
    move: ChoiceAnswer | None
    stats: Mapping[str, ChoiceAnswer]
    acts: float | None
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


def _target_result(response: JsonObject, target: str) -> tuple[_DecideResponse, _TargetResult]:
    try:
        parsed = _DecideResponse.model_validate(response)
    except ValidationError as error:
        raise DecideError(f"jevtester's response doesn't parse: {error}") from error
    result = next((r for r in parsed.results if r.target == target), None)
    if result is None:
        raise DecideError(f"jevtester's response has no result for {target}")
    return parsed, result


def _warnings(result: _TargetResult) -> tuple[str, ...]:
    return tuple(f"{w.code}: {w.message}" for w in result.warnings)


def _problem(result: _TargetResult, answer: ChoiceAnswer | None, question: str) -> str | None:
    """Return why there's no usable answer to the question that decides, or None."""
    if result.error is not None:
        return f"{result.error.code}: {result.error.message}"
    if answer is None:
        warnings = _warnings(result)
        return f"no usable {question} answer" + (f" ({'; '.join(warnings)})" if warnings else "")
    return None


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
    parsed, result = _target_result(response, target)
    warnings = _warnings(result)
    move = _usable_choice(parsed, result.answers, MOVE_QUESTION) if result.ok else None
    problem = _problem(result, move, MOVE_QUESTION)
    prefix = "stat_"
    stats: dict[str, ChoiceAnswer] = {}
    for question in result.answers:
        stat = _usable_choice(parsed, result.answers, question)
        if question.startswith(prefix) and stat is not None:
            stats[question.removeprefix(prefix)] = stat
    acts = result.answers.get(ACTS_QUESTION)
    return Decision(
        target=target,
        ok=move is not None,
        acts=acts.probability if isinstance(acts, NoulAnswer) else None,
        latency_ms=result.latency_ms,
        error=problem,
        move=move,
        stats=stats,
        warnings=warnings,
        response=response,
    )


@dataclass(frozen=True)
class OracleDecision:
    """One target's answers to an oracle question.

    Attributes:
        target: The target that answered.
        ok: True when there's a usable `kind` answer.
        latency_ms: How long the target took, or None when nothing was sent.
        error: Why there's no usable `kind` answer, when `ok` is False.
        kind: The `kind` answer: `yes_no`, `table`, or `cannot_tell`.
        likelihood: The `likelihood` answer, or None when it isn't usable.
        table: The `table` answer, or None when it isn't usable.
        warnings: jevtester's warnings, as `code: message`.
        response: The whole decide response, which case logging saves.
    """

    target: str
    ok: bool
    latency_ms: float | None
    error: str | None
    kind: ChoiceAnswer | None
    likelihood: ChoiceAnswer | None
    table: ChoiceAnswer | None
    warnings: tuple[str, ...]
    response: JsonObject = field(repr=False)


def parse_oracle_decision(response: JsonObject, target: str) -> OracleDecision:
    """Parse a decide response to an oracle request into one target's answers.

    An answer that names an option its question doesn't have is left out. Without a usable
    `kind` answer, the decision has `ok` False.

    Args:
        response: The decide response.
        target: The target to read.

    Returns:
        The target's answers.

    Raises:
        DecideError: If the response is malformed or has no result for the target.
    """
    parsed, result = _target_result(response, target)

    def usable(question: str) -> ChoiceAnswer | None:
        return _usable_choice(parsed, result.answers, question) if result.ok else None

    kind = usable(KIND_QUESTION)
    return OracleDecision(
        target=target,
        ok=kind is not None,
        latency_ms=result.latency_ms,
        error=_problem(result, kind, KIND_QUESTION),
        kind=kind,
        likelihood=usable(LIKELIHOOD_QUESTION),
        table=usable(TABLE_QUESTION),
        warnings=_warnings(result),
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
        return parse_decision(self.send(request, target), target)

    def decide_oracle(self, request: JsonObject, target: str) -> OracleDecision:
        """Send an oracle request to one target and parse its answers.

        Args:
            request: A body from
                [`build_oracle_request`][ironsworn_tui.decide.build_oracle_request].
            target: The target to send it to.

        Returns:
            The answers. A target that failed or timed out gives a decision with `ok` False.

        Raises:
            DecideError: If jevtester can't be reached, rejects the request, or sends a reply
                that doesn't parse.
        """
        return parse_oracle_decision(self.send(request, target), target)

    def send(self, request: JsonObject, target: str) -> JsonObject:
        """Send a request to one target and return jevtester's decide response.

        Raises:
            DecideError: If jevtester can't be reached, rejects the request, or sends a reply
                that isn't JSON.
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
        return response

    def add_case(self, suite: str, case: JsonObject, timeout_s: float = 5.0) -> None:
        """Add a case to the end of a suite's file.

        Args:
            suite: The suite's name, such as `play-exploring`.
            case: The case, with an id the suite doesn't have yet.
            timeout_s: Seconds to wait. It's short, because play waits for the save.

        Raises:
            DecideError: If jevtester can't be reached or refuses the case.
        """
        http_request = urllib.request.Request(
            f"{self.base_url}/api/suites/{suite}/cases",
            data=json.dumps(case).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _OPENER.open(http_request, timeout=timeout_s):
                return
        except urllib.error.HTTPError as error:
            raise DecideError(_error_message(error)) from error
        except (OSError, http.client.HTTPException) as error:
            raise DecideError(f"jevtester isn't reachable at {self.base_url}: {error}") from error


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
    log_path.parent.mkdir(parents=True, exist_ok=True)
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
