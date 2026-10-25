"""Descriptions of the `move` question's options, in two styles for the step 4 experiment."""

from enum import StrEnum

from ironsworn_tui.moves import ATTACK, CANNOT_TELL, NO_MOVE, Context, context_options
from ironsworn_tui.rules.datasworn import Datasworn


class CriteriaStyle(StrEnum):
    """How the `move` question describes each move."""

    GUIDE = "guide"
    """Short criteria written from the move disambiguation guide."""

    TRIGGER = "trigger"
    """The move's trigger text from the Datasworn data."""


_SPECIAL = {
    NO_MOVE: "Nothing risky or uncertain happens, so no move triggers",
    CANNOT_TELL: "The player's words don't show what the character does",
}

_GUIDE = {
    "face_danger": "Attempt something risky now, or react to an imminent threat",
    "secure_an_advantage": "Prepare, assess the situation, or gain leverage before acting",
    "gather_information": "Search, investigate, ask questions, study, or follow a track",
    "heal": "Treat an injury or ailment, your own or someone else's",
    "resupply": "Hunt, forage, or scavenge for food, gear, or ammunition",
    "make_camp": "Rest and recover for several hours in the wild",
    "undertake_a_journey": "Travel across hazardous or unfamiliar lands toward a destination",
    "reach_your_destination": "Arrive at the end of the current journey",
    "compel": "Persuade, bargain, intimidate, threaten, or lie to make someone do something",
    "sojourn": "Rest and seek help or recovery within a community",
    "draw_the_circle": "Challenge someone to a formal duel, or accept a challenge",
    "forge_a_bond": "Make a lasting bond with a person or community after time or hardship shared",
    "test_your_bond": "A bond is tested by conflict, betrayal, or circumstance",
    "swear_an_iron_vow": "Swear upon iron to complete a quest",
    "fulfill_your_vow": "Achieve what the character believes fulfills a vow",
    "forsake_your_vow": "Renounce a quest, break a promise, or give up on a goal that is lost",
    "enter_the_fray": "Start a fight: face off, ambush a foe, or get ambushed",
    "battle": "Fight a whole battle as one blur of action",
    "write_your_epilogue": "Retire from life as Ironsworn and tell how the story ends",
    ATTACK: "Attack a foe in the current fight, in close quarters or at range",
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
