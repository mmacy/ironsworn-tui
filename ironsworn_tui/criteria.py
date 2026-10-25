"""Descriptions of the options of the `move` question, in the recognizer experiment's two styles,
and of the oracle questions."""

from enum import StrEnum

from ironsworn_tui.moves import ATTACK, CANNOT_TELL, NO_MOVE, Context, context_options
from ironsworn_tui.oracles import ASKED_TABLES, LIKELIHOOD_OPTIONS
from ironsworn_tui.rules.datasworn import Datasworn


class CriteriaStyle(StrEnum):
    """How the `move` question describes each move."""

    GUIDE = "guide"
    """Short criteria written from the move disambiguation guide."""

    TRIGGER = "trigger"
    """The move's trigger text from the Datasworn data."""


# Each description is a concrete situation, so the model has something to match the state against.
# Where two moves get confused, the description names the line between them.
_SPECIAL = {
    NO_MOVE: (
        "The character does something with no risk and no doubt about the outcome, such as "
        "small talk with a friend over a meal in a safe place"
    ),
    CANNOT_TELL: (
        "The player only asks something out of character, or describes the scene or a feeling, "
        "and the character takes no action"
    ),
}

_GUIDE = {
    "face_danger": (
        "The character tries to overcome a danger or obstacle directly, or reacts to a threat "
        "about to hit"
    ),
    "secure_an_advantage": (
        "The character sizes up a threat or sets up an edge for an action still to come"
    ),
    "gather_information": (
        "The character searches, investigates, or questions people to learn facts about a "
        "mystery, place, or quest"
    ),
    "heal": "The character treats a wound or illness, their own or a companion's",
    "resupply": "The character hunts, forages, or scavenges for food and gear",
    "make_camp": (
        "The character camps away from any settlement, to rest and recover for the night"
    ),
    "undertake_a_journey": (
        "The character sets out or travels on through dangerous or unknown lands"
    ),
    "reach_your_destination": "The character arrives at the end of the journey under way",
    "compel": (
        "The character persuades, bargains with, threatens, or lies to someone to make them act"
    ),
    "sojourn": (
        "The character spends time in a community to recover, resupply, or get its people's help"
    ),
    "draw_the_circle": "The character challenges someone to a formal duel, or accepts a challenge",
    "forge_a_bond": (
        "The character seals a lasting bond with a person or community after time or hardship "
        "together"
    ),
    "test_your_bond": "A bond the character has made is strained by conflict, betrayal, or events",
    "swear_an_iron_vow": "The character swears upon iron to complete a quest",
    "fulfill_your_vow": "The character believes they have done what a sworn vow demands",
    "forsake_your_vow": (
        "The character abandons a vow, breaks a promise, or accepts its goal is lost"
    ),
    "enter_the_fray": (
        "A fight starts: the character faces off with a foe, ambushes one, or is ambushed"
    ),
    "battle": "The character fights a whole battle, told as one blur of action",
    "write_your_epilogue": (
        "The character retires from adventuring, and the player tells how their life ends"
    ),
    ATTACK: "The character attacks a foe in the fight under way, up close or at range",
}

_ATTACK_TRIGGER = "When you attack a foe in a fight..."


def move_criteria(data: Datasworn, context: Context, style: CriteriaStyle) -> dict[str, str]:
    """Return each `move` option's description for a context, in option order.

    Args:
        data: The Datasworn data, for the trigger text.
        context: The context.
        style: Which descriptions to use. `no_move` and `cannot_tell` read the same in both.

    Returns:
        The description of each option in
        [`context_options`][ironsworn_tui.moves.context_options], by option id.
    """
    criteria: dict[str, str] = {}
    for option in context_options(context):
        if option in _SPECIAL:
            criteria[option] = _SPECIAL[option]
        elif style is CriteriaStyle.GUIDE:
            criteria[option] = _GUIDE[option]
        elif option == ATTACK:
            criteria[option] = _ATTACK_TRIGGER
        else:
            criteria[option] = data.move(option).trigger.text
    return criteria


# The oracle questions. `kind` asks what sort of answer a question typed after `/oracle` wants,
# `likelihood` how likely a yes is, and `table` which table gives the answer. Code reads only
# the answer the `kind` answer calls for.
YES_NO = "yes_no"
TABLE = "table"

ORACLE_KIND_CRITERIA = {
    YES_NO: (
        "A yes or a no answers it, such as Is the bridge guarded? or Does the stranger know "
        "my name?"
    ),
    TABLE: (
        "It asks for a name, a place, a person, or an idea that a yes or a no can't give, "
        "such as What is the guard called? or What happens next?"
    ),
    CANNOT_TELL: (
        "It isn't a question about the story, such as a rules question or a note to the player"
    ),
}

LIKELIHOOD_CRITERIA = {
    "almost_certain": "The situation all but guarantees a yes",
    "likely": "A yes fits the situation better than a no",
    "fifty_fifty": "Nothing in the situation favors a yes or a no",
    "unlikely": "A no fits the situation better than a yes",
    "small_chance": "Only a surprise or a stroke of luck would give a yes",
}

_TABLE_CRITERIA = {
    "action": "What someone does or what happens next, as a verb such as Clash or Scheme",
    "theme": "What something is about, as a noun such as Risk or Ally",
    "role": "Who a person is or what they do for a living, such as a healer or a trader",
    "goal": "What a person wants, such as to obtain an object or to avenge a wrong",
    "descriptor": "What a person is like, such as stoic, cruel, or wary",
    "ironlander-name": "The name of a person of the Ironlands, such as a villager or a guard",
    "elf-name": "The name of an elf",
    "giant-name": "The name of a giant",
    "varou-name": "The name of a varou",
    "troll-name": "The name of a troll",
    "region": "Which region of the Ironlands somewhere is, such as the Deep Wilds",
    "location": "What kind of place somewhere is, such as a ruin, a mine, or a shrine",
    "coastal-location": "What kind of place is on the coast or the water, such as a fleet",
    "place-descriptor": "What a place looks or feels like, such as remote or haunted",
    "settlement-name": "The name of a town, village, or other settlement",
    "quick-name-prefix": "The first half of a settlement's name, such as Raven",
    "quick-name-suffix": "The second half of a settlement's name, such as ford",
    "settlement-trouble": "What trouble a settlement faces, such as dreadful omens or a feud",
    "plot-twist": "A surprise that turns the story, such as a trap that is sprung",
    "combat-action": "What a foe does next in a fight under way",
    "mystic-backlash": "What goes wrong when a ritual or magic fails",
    "challenge-rank": "How hard a foe, a journey, or a quest is, from troublesome to epic",
}


def likelihood_criteria() -> dict[str, str]:
    """Return the `likelihood` question's options and descriptions, most likely first."""
    return {option: LIKELIHOOD_CRITERIA[option] for option in LIKELIHOOD_OPTIONS}


def table_criteria() -> dict[str, str]:
    """Return the `table` question's options and descriptions, in the order the help lists them.

    There's no `cannot_tell` option. In the first oracle run it won 7 of the 33 questions a
    table fits, and those were all the table misses.
    """
    return {name: _TABLE_CRITERIA[name] for name in ASKED_TABLES}
