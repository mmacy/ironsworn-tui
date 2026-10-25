"""The recognizer experiment: hand-written phrasings turned into jevtester suites."""

import io
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator
from ruamel.yaml import YAML

from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import (
    ACTS_QUESTION,
    MOVE_QUESTION,
    RequestShape,
    TurnState,
    build_request,
)
from ironsworn_tui.moves import (
    CANNOT_TELL,
    Context,
    Initiative,
    context_options,
    stat_choices,
    stat_question_id,
)
from ironsworn_tui.rules.datasworn import Datasworn

PHRASINGS_FILE = (
    Path(__file__).resolve().parent.parent / "experiments" / "recognizer-phrasings.yaml"
)
SUITES_DIR = Path(__file__).resolve().parent.parent / "suites"
TARGETS = ("decision-1@foundry", "clef-flash@workers-ai")
# Claude wrote the phrasings, and the user approved them on 2026-10-24. jevtester ignores
# `claude-draft` cases.
PROVENANCE: Literal["human", "claude-draft"] = "human"


class Variant(BaseModel):
    """One way of asking the questions, run on every phrasing.

    Attributes:
        name: The name, which the suite and question set names end with.
        style: The criteria style.
        shape: How the request handles messages that don't fit an option.
        policy: The policy that turns the answers into an action.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    style: CriteriaStyle
    shape: RequestShape
    policy: str


VARIANTS = (
    Variant(name="guide", style=CriteriaStyle.GUIDE, shape=RequestShape(), policy="moves"),
    Variant(name="trigger", style=CriteriaStyle.TRIGGER, shape=RequestShape(), policy="moves"),
    Variant(
        name="guide-stat-abstain",
        style=CriteriaStyle.GUIDE,
        shape=RequestShape(stat_abstain=True),
        policy="moves",
    ),
    Variant(
        name="guide-acts",
        style=CriteriaStyle.GUIDE,
        shape=RequestShape(stat_abstain=True, acts_question=True),
        policy="moves-acts",
    ),
)


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Character(_Strict):
    """A character the phrasings use."""

    name: str
    character: str


class Phrasing(_Strict):
    """One player message and the move and stat it should trigger.

    Attributes:
        id: The case id, unique within its context.
        character: The key of a character in the file's `characters`.
        situation: The scene line.
        initiative: Who has initiative, for a fight phrasing.
        says: What the player types.
        move: The expected `move` option.
        also: Other `move` options that count as correct, for a phrasing with two fair readings.
        stat: The expected stat, when the move has a stat question.
        tags: Labels for grouping results, such as `fd-vs-saa`.
    """

    id: str
    character: str
    situation: str
    initiative: Initiative | None = None
    says: str
    move: str
    also: tuple[str, ...] = ()
    stat: str | None = None
    tags: tuple[str, ...] = ()


class Phrasings(_Strict):
    """The phrasings file: the characters, and the phrasings for each context."""

    characters: dict[str, Character]
    exploring: tuple[Phrasing, ...]
    journey: tuple[Phrasing, ...]
    fight: tuple[Phrasing, ...]

    def for_context(self, context: Context) -> tuple[Phrasing, ...]:
        """Return the phrasings for a context."""
        return getattr(self, context.value)

    @model_validator(mode="after")
    def _check_references(self) -> Phrasings:
        for context in Context:
            ids = [phrasing.id for phrasing in self.for_context(context)]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{context}: phrasing ids repeat")
            options = context_options(context)
            for phrasing in self.for_context(context):
                if phrasing.character not in self.characters:
                    raise ValueError(f"{phrasing.id}: unknown character {phrasing.character}")
                for move in (phrasing.move, *phrasing.also):
                    if move not in options:
                        raise ValueError(f"{phrasing.id}: {move} isn't a {context} option")
        return self


def load_phrasings(path: Path = PHRASINGS_FILE) -> Phrasings:
    """Read and validate the phrasings file."""
    loader: Any = YAML(typ="safe", pure=True)
    return Phrasings.model_validate(loader.load(path))


def turn_state(phrasings: Phrasings, context: Context, phrasing: Phrasing) -> TurnState:
    """Return the turn state for a phrasing, as play would build it."""
    character = phrasings.characters[phrasing.character]
    return TurnState(
        name=character.name,
        character=character.character,
        situation=phrasing.situation,
        context=context,
        initiative=phrasing.initiative,
        player_says=phrasing.says,
    )


def question_set_name(context: Context, variant: Variant) -> str:
    """Return the name of a question set, such as `moves-exploring-guide`."""
    return f"moves-{context.value}-{variant.name}"


def suite_name(context: Context, variant: Variant) -> str:
    """Return the name of a recognizer suite, such as `recognizer-exploring-guide`."""
    return f"recognizer-{context.value}-{variant.name}"


def question_set(data: Datasworn, context: Context, variant: Variant) -> dict[str, Any]:
    """Return a question set with the questions play sends in a context.

    The questions don't depend on the state, so any state for the context gives the same ones.
    """
    state = TurnState(
        name="",
        character="",
        situation="",
        context=context,
        initiative="character" if context is Context.FIGHT else None,
        player_says="",
    )
    questions = build_request(data, state, variant.style, variant.shape)["questions"]
    return {"name": question_set_name(context, variant), "questions": questions}


def _case(
    data: Datasworn, phrasings: Phrasings, context: Context, phrasing: Phrasing, variant: Variant
) -> dict[str, Any]:
    expected: dict[str, Any] = {}
    if variant.shape.acts_question:
        expected[ACTS_QUESTION] = {"answer": phrasing.move != CANNOT_TELL}
    if not (variant.shape.acts_question and phrasing.move == CANNOT_TELL):
        expected[MOVE_QUESTION] = {"answer": phrasing.move}
        if phrasing.also:
            expected[MOVE_QUESTION]["acceptable"] = list(phrasing.also)
    stats = stat_choices(data, phrasing.move)
    if stats:
        if phrasing.stat is None:
            raise ValueError(f"{phrasing.id}: {phrasing.move} needs an expected stat")
        if phrasing.stat not in {choice.stat for choice in stats}:
            raise ValueError(f"{phrasing.id}: {phrasing.stat} isn't a {phrasing.move} stat")
        expected[stat_question_id(phrasing.move)] = {"answer": phrasing.stat}
    elif phrasing.stat is not None:
        raise ValueError(f"{phrasing.id}: {phrasing.move} has no stat question")
    return {
        "id": phrasing.id,
        "state": turn_state(phrasings, context, phrasing).to_json(),
        "expected": expected,
        "expected_action": phrasing.move,
        "tags": list(phrasing.tags),
        "provenance": PROVENANCE,
    }


def suite(
    data: Datasworn, phrasings: Phrasings, context: Context, variant: Variant
) -> dict[str, Any]:
    """Return a recognizer suite: a context's phrasings asked one way.

    With the `acts` question, a `cannot_tell` phrasing expects `acts` to be no and expects
    nothing of the `move` question, which has no `cannot_tell` option.

    Raises:
        ValueError: If a phrasing's expected stat doesn't fit its move.
    """
    cases = [_case(data, phrasings, context, p, variant) for p in phrasings.for_context(context)]
    return {
        "name": suite_name(context, variant),
        "question_set": question_set_name(context, variant),
        "policy": variant.policy,
        "targets": list(TARGETS),
        "cases": cases,
    }


def dump_yaml(document: dict[str, Any]) -> str:
    """Return a document as YAML, in the key order given."""
    dumper: Any = YAML()
    dumper.width = 4096
    dumper.indent(mapping=2, sequence=4, offset=2)
    out = io.StringIO()
    dumper.dump(document, out)
    return out.getvalue()


def generated_files(data: Datasworn, phrasings: Phrasings) -> dict[Path, str]:
    """Return every generated question set and suite, by path relative to `suites/`."""
    files: dict[Path, str] = {}
    for context in Context:
        for variant in VARIANTS:
            name = question_set_name(context, variant)
            files[Path("question-sets") / f"{name}.yaml"] = dump_yaml(
                question_set(data, context, variant)
            )
            files[Path(f"{suite_name(context, variant)}.yaml")] = dump_yaml(
                suite(data, phrasings, context, variant)
            )
    return files
