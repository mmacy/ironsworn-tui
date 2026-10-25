"""Turns a decision into a suggestion, with the thresholds from the `moves` policy."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ruamel.yaml import YAML

from ironsworn_tui.decide import Decision
from ironsworn_tui.moves import CANNOT_TELL, NO_MOVE, Context, context_options

POLICY_FILE = Path(__file__).resolve().parent.parent / "suites" / "policies" / "moves.yaml"
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
    loader: Any = YAML(typ="safe", pure=True)
    policy: dict[str, Any] = loader.load(path)
    values: dict[str, float] = {
        **policy["thresholds"],
        **policy.get("per_target", {}).get(target, {}),
    }
    return Thresholds(act=values["act"], confirm=values["confirm"])


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
