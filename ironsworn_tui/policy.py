"""Turns a decision into a suggestion, with the thresholds from the `moves` and `oracle`
policies."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ruamel.yaml import YAML

from ironsworn_tui.criteria import YES_NO
from ironsworn_tui.decide import ChoiceAnswer, Decision, OracleDecision
from ironsworn_tui.moves import CANNOT_TELL, NO_MOVE, Context, context_options
from ironsworn_tui.oracles import ASKED_TABLES, LIKELIHOOD_OPTIONS

POLICIES = Path(__file__).resolve().parent.parent / "suites" / "policies"
POLICY_FILE = POLICIES / "moves.yaml"
ORACLE_POLICY_FILE = POLICIES / "oracle.yaml"
TOP_TWO = 2

type Band = Literal["act", "confirm", "escalate", "no_roll"]


@dataclass(frozen=True)
class Thresholds:
    """The `move` question's confidence thresholds for one target.

    Attributes:
        act: At or above it, the suggestion bar preselects the move.
        confirm: At or above it, the bar shows the top two moves. Below it, the full list.
    """

    act: float
    confirm: float


def load_thresholds(target: str, path: Path = POLICY_FILE) -> Thresholds:
    """Read the `act` and `confirm` thresholds for a target from the policy file.

    A target's `per_target` values replace the shared ones.
    """
    values = _thresholds(target, path)
    return Thresholds(act=values["act"], confirm=values["confirm"])


def _thresholds(target: str, path: Path) -> dict[str, float]:
    loader: Any = YAML(typ="safe", pure=True)
    policy: dict[str, Any] = loader.load(path)
    return {**policy["thresholds"], **policy.get("per_target", {}).get(target, {})}


@dataclass(frozen=True)
class OracleThresholds:
    """The oracle questions' thresholds for one target.

    Attributes:
        act: The lowest confidence in the `kind` answer at which the suggestion bar
            preselects a likelihood or a table.
        pick: The lowest probability of the chosen likelihood or table at which the bar
            preselects it.
    """

    act: float
    pick: float


def load_oracle_thresholds(target: str, path: Path = ORACLE_POLICY_FILE) -> OracleThresholds:
    """Read the `act` and `pick` thresholds for a target from the oracle policy file."""
    values = _thresholds(target, path)
    return OracleThresholds(act=values["act"], pick=values["pick"])


@dataclass(frozen=True)
class Suggestion:
    """What the suggestion bar offers for a message.

    Attributes:
        band: `act` preselects the one option; `confirm` offers the top two; `escalate`
            offers the full list; `no_roll` means the top answer is `no_move` or
            `cannot_tell`, so the message is logged without a roll and the full list is
            offered.
        options: The `move` options offered, most probable first.
        decision: The decision, or None when the request failed.
        note: Why there's no suggestion, when the request failed.
    """

    band: Band
    options: tuple[str, ...]
    decision: Decision | None
    note: str | None = None


def _moves_only(options: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(option for option in options if option not in (NO_MOVE, CANNOT_TELL))


def suggest(decision: Decision | None, context: Context, thresholds: Thresholds) -> Suggestion:
    """Decide what the suggestion bar offers for a decision.

    Args:
        decision: The decision, or None when jevtester couldn't be reached.
        context: The context, for the full option list.
        thresholds: The policy's thresholds for the target.

    Returns:
        The suggestion.
    """
    full = _moves_only(context_options(context))
    if decision is None or decision.move is None:
        return Suggestion(band="escalate", options=full, decision=decision)
    ranked = tuple(option for option, _ in decision.move.ranked())
    if decision.move.choice in (NO_MOVE, CANNOT_TELL):
        return Suggestion(band="no_roll", options=_moves_only(ranked), decision=decision)
    confidence = decision.move.confidence
    if confidence >= thresholds.act:
        return Suggestion(band="act", options=(decision.move.choice,), decision=decision)
    if confidence >= thresholds.confirm:
        return Suggestion(band="confirm", options=_moves_only(ranked)[:TOP_TWO], decision=decision)
    return Suggestion(band="escalate", options=_moves_only(ranked), decision=decision)


type OracleBand = Literal["act", "escalate"]

FULL_ORACLE_LIST = (*ASKED_TABLES, *LIKELIHOOD_OPTIONS)


@dataclass(frozen=True)
class OracleSuggestion:
    """What the suggestion bar offers for a question typed after `/oracle`.

    Attributes:
        question: The question, which the log keeps with the answer.
        band: `act` preselects the first option; `escalate` preselects nothing.
        options: The likelihood option ids and table names offered. The kind the model
            chose comes first, each kind most probable first. Without a usable answer, every
            table comes first in the help's order, then the likelihoods.
        decision: The decision, or None when the request failed or wasn't sent.
        note: Why there's no suggestion, when the request failed.
    """

    question: str
    band: OracleBand
    options: tuple[str, ...]
    decision: OracleDecision | None
    note: str | None = None


def _ranked(answer: ChoiceAnswer | None, options: tuple[str, ...]) -> tuple[str, ...]:
    if answer is None:
        return options
    return tuple(sorted(options, key=lambda option: -answer.probabilities.get(option, 0.0)))


def suggest_oracle(
    decision: OracleDecision | None, question: str, thresholds: OracleThresholds
) -> OracleSuggestion:
    """Decide what the suggestion bar offers for an oracle question.

    Args:
        decision: The decision, or None when jevtester couldn't be reached or wasn't asked.
        question: The question.
        thresholds: The oracle policy's thresholds for the target.

    Returns:
        The suggestion. It preselects the likelihood or table when the `kind` answer's
        confidence is at least `act` and the chosen option's probability at least `pick`.
    """
    kind = decision.kind if decision is not None else None
    if decision is None or kind is None or kind.choice == CANNOT_TELL:
        return OracleSuggestion(question, "escalate", FULL_ORACLE_LIST, decision)
    likelihoods = _ranked(decision.likelihood, tuple(LIKELIHOOD_OPTIONS))
    tables = _ranked(decision.table, ASKED_TABLES)
    yes_no = kind.choice == YES_NO
    options = (*likelihoods, *tables) if yes_no else (*tables, *likelihoods)
    answer = decision.likelihood if yes_no else decision.table
    sure = (
        answer is not None
        and kind.confidence >= thresholds.act
        and answer.probabilities[answer.choice] >= thresholds.pick
        and options[0] == answer.choice
    )
    return OracleSuggestion(question, "act" if sure else "escalate", options, decision)
