"""Saves each turn the decision model answered as a jevtester case, labeled with what the
player did."""

import re
from datetime import UTC, datetime
from typing import Any, Protocol

from ironsworn_tui.criteria import TABLE, YES_NO
from ironsworn_tui.decide import (
    KIND_QUESTION,
    LIKELIHOOD_QUESTION,
    MOVE_QUESTION,
    TABLE_QUESTION,
    Decision,
    JsonObject,
    OracleDecision,
)
from ironsworn_tui.moves import CANNOT_TELL, NO_MOVE, Context, stat_choices, stat_question_id
from ironsworn_tui.oracles import LIKELIHOOD_OPTIONS
from ironsworn_tui.rules.datasworn import Datasworn, Stat

CORRECTED = "corrected"
ORACLE_SUITE = "play-oracle"
ABSTAINED = "abstained"


class CaseSink(Protocol):
    """Anything that saves a case to a suite, such as a `JevtesterClient`."""

    def add_case(self, suite: str, case: JsonObject) -> None:
        """Add a case to the end of a suite."""
        ...


def play_suite_name(context: Context) -> str:
    """Return the name of the suite play adds cases to, such as `play-exploring`."""
    return f"play-{context.value}"


def case_id(name: str, now: datetime | None = None) -> str:
    """Return a case id from the character's name and the time, unique to the microsecond."""
    moment = now or datetime.now(UTC)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "turn"
    return f"{slug}-{moment:%Y%m%dT%H%M%S%f}"


def build_case(
    data: Datasworn, decision: Decision, option: str, stat: Stat | None, id_: str
) -> JsonObject:
    """Build the case for a turn: the state the model saw, and what the player did.

    Args:
        data: The Datasworn data, to tell whether the option has a stat question.
        decision: The model's answers, with the request it was asked.
        option: The `move` option the player rolled, or `no_move`.
        stat: The stat the player rolled with.
        id_: The case's id.

    Returns:
        The case, as `POST /api/suites/{name}/cases` takes it. When the player didn't take
        the model's top `move` answer, it has the `abstained` tag if that answer was
        `cannot_tell`, and the `corrected` tag otherwise.
    """
    request: dict[str, Any] = decision.response["request"]
    expected: JsonObject = {MOVE_QUESTION: {"answer": option}}
    if stat is not None and option != NO_MOVE and stat_choices(data, option):
        expected[stat_question_id(option)] = {"answer": stat}
    tags: list[str] = []
    if decision.move is not None and decision.move.choice != option:
        tags.append(ABSTAINED if decision.move.choice == CANNOT_TELL else CORRECTED)
    return {
        "id": id_,
        "state": request["state"],
        "expected": expected,
        "expected_action": option,
        "tags": tags,
        "provenance": "human",
    }


def build_oracle_case(decision: OracleDecision, option: str, id_: str) -> JsonObject:
    """Build the case for an oracle question: the state the model saw, and what the player
    rolled.

    Args:
        decision: The model's answers, with the request it was asked.
        option: The likelihood option id or the table name the player rolled.
        id_: The case's id.

    Returns:
        The case for the `play-oracle` suite. When the player didn't roll the model's top
        answer, it has the `abstained` tag if the `kind` answer was `cannot_tell`, and the
        `corrected` tag otherwise.
    """
    request: dict[str, Any] = decision.response["request"]
    yes_no = option in LIKELIHOOD_OPTIONS
    expected: JsonObject = {
        KIND_QUESTION: {"answer": YES_NO if yes_no else TABLE},
        LIKELIHOOD_QUESTION if yes_no else TABLE_QUESTION: {"answer": option},
    }
    tags: list[str] = []
    kind = decision.kind
    if kind is not None and kind.choice == CANNOT_TELL:
        tags.append(ABSTAINED)
    elif kind is not None:
        top = decision.likelihood if kind.choice == YES_NO else decision.table
        if top is None or top.choice != option:
            tags.append(CORRECTED)
    return {
        "id": id_,
        "state": request["state"],
        "expected": expected,
        "expected_action": option,
        "tags": tags,
        "provenance": "human",
    }
