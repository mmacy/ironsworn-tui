"""The recognizer experiments: hand-written player messages and oracle questions turned into
jevtester suites."""

import io
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator
from ruamel.yaml import YAML

from ironsworn_tui.cases import ORACLE_SUITE, play_suite_name
from ironsworn_tui.criteria import TABLE, YES_NO, CriteriaStyle, likelihood_criteria, table_criteria
from ironsworn_tui.decide import (
    ACTS_QUESTION,
    KIND_QUESTION,
    LIKELIHOOD_QUESTION,
    MOVE_QUESTION,
    TABLE_QUESTION,
    OracleState,
    RequestShape,
    TurnState,
    build_oracle_request,
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
ORACLE_PHRASINGS_FILE = (
    Path(__file__).resolve().parent.parent / "experiments" / "oracle-phrasings.yaml"
)
SUITES_DIR = Path(__file__).resolve().parent.parent / "suites"
ORACLE_QUESTION_SET = "oracle"
ORACLE_POLICY = "oracle"
ORACLE_RECOGNIZER = "recognizer-oracle"
# The oracle policy's action when no table or likelihood should be preselected.
ESCALATE = "escalate"
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


type Kind = Literal["yes_no", "table", "cannot_tell"]


class OracleQuestion(_Strict):
    """One question typed after `/oracle`, and the answers it should get.

    Attributes:
        id: The case id.
        character: The key of a character in the file's `characters`.
        situation: The scene line.
        asks: What the player types after `/oracle`.
        kind: `yes_no`, `table`, or `cannot_tell`.
        also_kind: Other kinds that count as correct.
        likelihood: The expected `likelihood` option, for a yes or no question.
        also_likelihood: Other likelihoods that count as correct.
        table: The expected `table` option, for a table question. A table question without one
            is a question no table fits, which the policy should escalate.
        also_table: Other tables that count as correct.
        tags: Labels for grouping results.
    """

    id: str
    character: str
    situation: str
    asks: str
    kind: Kind
    also_kind: tuple[Kind, ...] = ()
    likelihood: str | None = None
    also_likelihood: tuple[str, ...] = ()
    table: str | None = None
    also_table: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_answers(self) -> OracleQuestion:
        if self.kind == YES_NO and self.likelihood is None:
            raise ValueError(f"{self.id}: a yes_no question needs a likelihood")
        likelihoods = likelihood_criteria()
        for likelihood in (*([self.likelihood] if self.likelihood else []), *self.also_likelihood):
            if likelihood not in likelihoods:
                raise ValueError(f"{self.id}: unknown likelihood {likelihood}")
        tables = table_criteria()
        for table in (*([self.table] if self.table else []), *self.also_table):
            if table not in tables:
                raise ValueError(f"{self.id}: unknown table {table}")
        return self

    @property
    def action(self) -> str:
        """The action the oracle policy should choose: the likelihood, the table, or
        `escalate`."""
        if self.kind == YES_NO and self.likelihood is not None:
            return self.likelihood
        if self.kind == TABLE and self.table is not None:
            return self.table
        return ESCALATE


class OraclePhrasings(_Strict):
    """The oracle questions file: the characters, and the questions."""

    characters: dict[str, Character]
    questions: tuple[OracleQuestion, ...]

    @model_validator(mode="after")
    def _check_references(self) -> OraclePhrasings:
        ids = [question.id for question in self.questions]
        if len(set(ids)) != len(ids):
            raise ValueError("oracle question ids repeat")
        for question in self.questions:
            if question.character not in self.characters:
                raise ValueError(f"{question.id}: unknown character {question.character}")
        return self


def load_oracle_phrasings(path: Path = ORACLE_PHRASINGS_FILE) -> OraclePhrasings:
    """Read and validate the oracle questions file."""
    loader: Any = YAML(typ="safe", pure=True)
    return OraclePhrasings.model_validate(loader.load(path))


def oracle_state(phrasings: OraclePhrasings, question: OracleQuestion) -> OracleState:
    """Return the oracle state for a question, as play would build it."""
    return OracleState(
        character=phrasings.characters[question.character].character,
        situation=question.situation,
        question=question.asks,
    )


def oracle_question_set() -> dict[str, Any]:
    """Return the question set play sends for a question typed after `/oracle`."""
    state = OracleState(character="", situation="", question="")
    return {"name": ORACLE_QUESTION_SET, "questions": build_oracle_request(state)["questions"]}


def _expect(answer: str, acceptable: tuple[str, ...]) -> dict[str, Any]:
    expected: dict[str, Any] = {"answer": answer}
    if acceptable:
        expected["acceptable"] = list(acceptable)
    return expected


def _oracle_case(phrasings: OraclePhrasings, question: OracleQuestion) -> dict[str, Any]:
    expected = {KIND_QUESTION: _expect(question.kind, question.also_kind)}
    if question.likelihood is not None:
        expected[LIKELIHOOD_QUESTION] = _expect(question.likelihood, question.also_likelihood)
    if question.table is not None:
        expected[TABLE_QUESTION] = _expect(question.table, question.also_table)
    return {
        "id": question.id,
        "state": oracle_state(phrasings, question).to_json(),
        "expected": expected,
        "expected_action": question.action,
        "tags": [question.kind, *question.tags],
        "provenance": PROVENANCE,
    }


def oracle_suite(phrasings: OraclePhrasings) -> dict[str, Any]:
    """Return the oracle recognizer suite: every hand-written oracle question."""
    return {
        "name": ORACLE_RECOGNIZER,
        "question_set": ORACLE_QUESTION_SET,
        "policy": ORACLE_POLICY,
        "targets": list(TARGETS),
        "cases": [_oracle_case(phrasings, question) for question in phrasings.questions],
    }


def play_oracle_suite() -> dict[str, Any]:
    """Return an empty play suite for oracle questions, which play adds a case to after each
    answered question."""
    return {
        "name": ORACLE_SUITE,
        "question_set": ORACLE_QUESTION_SET,
        "policy": ORACLE_POLICY,
        "targets": list(TARGETS),
        "cases": [],
    }


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


def play_suite(context: Context) -> dict[str, Any]:
    """Return an empty play suite, which play adds a case to after each answered turn.

    Its question set is the one play sends: the guide criteria with the default shape.
    """
    guide = next(variant for variant in VARIANTS if variant.name == "guide")
    return {
        "name": play_suite_name(context),
        "question_set": question_set_name(context, guide),
        "policy": guide.policy,
        "targets": list(TARGETS),
        "cases": [],
    }


def generated_files(
    data: Datasworn, phrasings: Phrasings, oracle: OraclePhrasings
) -> dict[Path, str]:
    """Return every generated question set and suite, by path relative to `suites/`."""
    files: dict[Path, str] = {
        Path("question-sets") / f"{ORACLE_QUESTION_SET}.yaml": dump_yaml(oracle_question_set()),
        Path(f"{ORACLE_RECOGNIZER}.yaml"): dump_yaml(oracle_suite(oracle)),
    }
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
