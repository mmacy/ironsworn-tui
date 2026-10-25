"""Which moves the chat can trigger, by context, and the stat question for each."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from ironsworn_tui.rules.datasworn import Datasworn, Stat, StatOption

ATTACK = "attack"
NO_MOVE = "no_move"
CANNOT_TELL = "cannot_tell"

type Initiative = Literal["character", "foe"]


class MoveGroup(StrEnum):
    """How a move starts in the app."""

    FICTION = "fiction"
    """Triggered by what the player types. These are the `move` question's options."""

    AFTER_RESULT = "after_result"
    """Offered as a key on the roll card after a result."""

    OUTCOME = "outcome"
    """Run by the app when a result calls for it."""

    COMMAND = "command"
    """Started by the player with a command."""


_GROUPS: dict[MoveGroup, tuple[str, ...]] = {
    MoveGroup.FICTION: (
        "face_danger",
        "secure_an_advantage",
        "gather_information",
        "heal",
        "resupply",
        "make_camp",
        "undertake_a_journey",
        "reach_your_destination",
        "compel",
        "sojourn",
        "draw_the_circle",
        "forge_a_bond",
        "test_your_bond",
        "swear_an_iron_vow",
        "fulfill_your_vow",
        "forsake_your_vow",
        "enter_the_fray",
        "strike",
        "clash",
        "battle",
        "write_your_epilogue",
    ),
    MoveGroup.AFTER_RESULT: ("end_the_fight",),
    MoveGroup.OUTCOME: (
        "pay_the_price",
        "endure_harm",
        "endure_stress",
        "companion_endure_harm",
        "face_death",
        "face_desolation",
        "out_of_supply",
        "face_a_setback",
    ),
    MoveGroup.COMMAND: ("turn_the_tide", "ask_the_oracle", "reach_a_milestone", "advance"),
}

_GROUP_OF = {move_id: group for group, move_ids in _GROUPS.items() for move_id in move_ids}


def move_group(data: Datasworn, move_id: str) -> MoveGroup | None:
    """Return a move's group.

    Args:
        data: The Datasworn data.
        move_id: The move id, such as `face_danger`.

    Returns:
        The group, or None for a move the app leaves out (Aid Your Ally).

    Raises:
        UnknownIdError: If no move has the id.
    """
    data.move(move_id)
    return _GROUP_OF.get(move_id)


class Context(StrEnum):
    """The situation that decides which moves the chat offers."""

    EXPLORING = "exploring"
    """No fight and no journey."""

    JOURNEY = "journey"
    """A journey is active, and there's no fight."""

    FIGHT = "fight"
    """A fight is active, whether or not a journey is."""


# Battle can replace a whole fight, so it stays outside one (rulebook page 84).
_FIGHT_ONLY = {"strike", "clash"}

_EXPLORING = tuple(
    move_id
    for move_id in _GROUPS[MoveGroup.FICTION]
    if move_id not in _FIGHT_ONLY and move_id != "reach_your_destination"
)
_JOURNEY = (*_EXPLORING, "reach_your_destination")
_FIGHT = (
    ATTACK,
    "battle",
    "face_danger",
    "secure_an_advantage",
    "gather_information",
    "compel",
    "heal",
    "forsake_your_vow",
)

_OPTIONS: dict[Context, tuple[str, ...]] = {
    Context.EXPLORING: (*_EXPLORING, NO_MOVE, CANNOT_TELL),
    Context.JOURNEY: (*_JOURNEY, NO_MOVE, CANNOT_TELL),
    Context.FIGHT: (*_FIGHT, NO_MOVE, CANNOT_TELL),
}


def context_options(context: Context) -> tuple[str, ...]:
    """Return the `move` question's options for a context.

    The order is fixed, so the jevtester suite for a context matches what play sends.

    Args:
        context: The context.

    Returns:
        Move ids, plus `attack` in a fight (Strike or Clash, by initiative), then `no_move` (the
        action has no risk) and `cannot_tell`.
    """
    return _OPTIONS[context]


def attack_move(initiative: Initiative) -> str:
    """Return the move an attack makes: Strike with initiative, Clash without it.

    Args:
        initiative: Who has initiative in the fight.

    Returns:
        `strike` or `clash`.
    """
    return "strike" if initiative == "character" else "clash"


def resolve_option(option: str, initiative: Initiative | None) -> str | None:
    """Return the move a `move` option makes.

    Args:
        option: A `move` option from [`context_options`][ironsworn_tui.moves.context_options].
        initiative: Who has initiative, or None outside a fight.

    Returns:
        The move id, or None for `no_move` and `cannot_tell`, which make no roll.

    Raises:
        ValueError: If the option is `attack` and there's no fight.
    """
    if option in (NO_MOVE, CANNOT_TELL):
        return None
    if option == ATTACK:
        if initiative is None:
            raise ValueError("an attack needs a fight with initiative set")
        return attack_move(initiative)
    return option


@dataclass(frozen=True)
class StatChoice:
    """One approach a move offers, and the stat it rolls with.

    Attributes:
        stat: The stat.
        text: The approach, from the move data, such as "With speed, agility, or precision".
    """

    stat: Stat
    text: str


def stat_choices(data: Datasworn, option: str) -> tuple[StatChoice, ...]:
    """Return the approaches a stat question offers for a `move` option.

    A move gets a stat question when it has two or more `player_choice`
    [`Condition`][ironsworn_tui.rules.datasworn.Condition]s with text. `attack` uses Strike's
    approach texts, and Clash offers the same stats. After
    [`resolve_option`][ironsworn_tui.moves.resolve_option] picks Clash, show Clash's own text.

    Args:
        data: The Datasworn data.
        option: A `move` option, such as `face_danger` or `attack`.

    Returns:
        The approaches, in the order the move data lists them, or an empty tuple for an option
        with no stat question. Each approach's stat is the option id in the stat question.

    Raises:
        UnknownIdError: If the option isn't a move id or a special option.
        ValueError: If an approach with text rolls something other than one stat.
    """
    if option in (NO_MOVE, CANNOT_TELL):
        return ()
    move = data.move("strike" if option == ATTACK else option)
    choices: list[StatChoice] = []
    for condition in move.trigger.conditions:
        if condition.method != "player_choice" or condition.text is None:
            continue
        match condition.roll_options:
            case (StatOption(stat=stat),):
                choices.append(StatChoice(stat=stat, text=condition.text))
            case _:
                raise ValueError(f"{move.id}: {condition.text!r} doesn't roll one stat")
    return tuple(choices) if len(choices) >= 2 else ()


def stat_question_id(option: str) -> str:
    """Return the id of the stat question for a `move` option, such as `stat_face_danger`."""
    return f"stat_{option}"


def stat_question_options(data: Datasworn, context: Context) -> tuple[str, ...]:
    """Return the `move` options in a context that get a stat question.

    Args:
        data: The Datasworn data.
        context: The context.

    Returns:
        The options, in the context's option order.
    """
    return tuple(option for option in context_options(context) if stat_choices(data, option))
