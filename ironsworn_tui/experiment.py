"""The recognizer experiment: hand-written phrasings turned into jevtester suites."""

import io
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator
from ruamel.yaml import YAML

from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import MOVE_QUESTION, TurnState, build_request
from ironsworn_tui.moves import Context, Initiative, context_options, stat_choices, stat_question_id
from ironsworn_tui.rules.datasworn import Datasworn

PHRASINGS_FILE = (
    Path(__file__).resolve().parent.parent / "experiments" / "recognizer-phrasings.yaml"
)
SUITES_DIR = Path(__file__).resolve().parent.parent / "suites"
POLICY = "moves"
TARGETS = ("decision-1@foundry",)
# jevtester ignores cases Claude wrote until a person approves them by changing this to "human".
PROVENANCE: Literal["human", "claude-draft"] = "claude-draft"


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


def question_set_name(context: Context, style: CriteriaStyle) -> str:
    """Return the name of a question set, such as `moves-exploring-guide`."""
    return f"moves-{context.value}-{style.value}"


def suite_name(context: Context, style: CriteriaStyle) -> str:
    """Return the name of a recognizer suite, such as `recognizer-exploring-guide`."""
    return f"recognizer-{context.value}-{style.value}"


def question_set(data: Datasworn, context: Context, style: CriteriaStyle) -> dict[str, Any]:
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
    questions = build_request(data, state, style)["questions"]
    return {"name": question_set_name(context, style), "questions": questions}


def _case(
    data: Datasworn, phrasings: Phrasings, context: Context, phrasing: Phrasing
) -> dict[str, Any]:
    expected: dict[str, Any] = {MOVE_QUESTION: {"answer": phrasing.move}}
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
    data: Datasworn, phrasings: Phrasings, context: Context, style: CriteriaStyle
) -> dict[str, Any]:
    """Return a recognizer suite: a context's phrasings asked with one criteria style.

    Raises:
        ValueError: If a phrasing's expected stat doesn't fit its move.
    """
    return {
        "name": suite_name(context, style),
        "question_set": question_set_name(context, style),
        "policy": POLICY,
        "targets": list(TARGETS),
        "cases": [_case(data, phrasings, context, p) for p in phrasings.for_context(context)],
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
        for style in CriteriaStyle:
            name = question_set_name(context, style)
            files[Path("question-sets") / f"{name}.yaml"] = dump_yaml(
                question_set(data, context, style)
            )
            files[Path(f"{suite_name(context, style)}.yaml")] = dump_yaml(
                suite(data, phrasings, context, style)
            )
    return files
