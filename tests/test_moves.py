"""Move groups, contexts, and stat questions."""

import pytest

from ironsworn_tui.moves import (
    ATTACK,
    CANNOT_TELL,
    NO_MOVE,
    Context,
    Initiative,
    MoveGroup,
    attack_move,
    context_options,
    move_group,
    resolve_option,
    stat_choices,
    stat_question_id,
    stat_question_options,
)
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.errors import UnknownIdError

SPECIAL_OPTIONS = {ATTACK, NO_MOVE, CANNOT_TELL}


def test_every_move_but_aid_your_ally_has_one_group():
    data = datasworn()
    grouped = {move_id for move_id in data.moves if move_group(data, move_id) is not None}
    assert set(data.moves) - grouped == {"aid_your_ally"}


@pytest.mark.parametrize(
    ("group", "count"),
    [
        (MoveGroup.FICTION, 21),
        (MoveGroup.AFTER_RESULT, 1),
        (MoveGroup.OUTCOME, 8),
        (MoveGroup.COMMAND, 4),
    ],
)
def test_group_sizes(group: MoveGroup, count: int):
    assert sum(move_group(datasworn(), move_id) is group for move_id in datasworn().moves) == count


def test_groups_of_named_moves():
    assert move_group(datasworn(), "end_the_fight") is MoveGroup.AFTER_RESULT
    assert move_group(datasworn(), "face_a_setback") is MoveGroup.OUTCOME
    assert move_group(datasworn(), "turn_the_tide") is MoveGroup.COMMAND
    assert move_group(datasworn(), "strike") is MoveGroup.FICTION
    assert move_group(datasworn(), "aid_your_ally") is None


@pytest.mark.parametrize(
    ("context", "count"),
    [(Context.EXPLORING, 20), (Context.JOURNEY, 21), (Context.FIGHT, 10)],
)
def test_context_sizes(context: Context, count: int):
    assert len(context_options(context)) == count


@pytest.mark.parametrize("context", list(Context))
def test_every_option_is_a_real_move_or_a_special_option(context: Context):
    data = datasworn()
    for option in context_options(context):
        assert option in data.moves or option in SPECIAL_OPTIONS


@pytest.mark.parametrize("context", list(Context))
def test_options_are_unique_and_end_with_no_move_and_cannot_tell(context: Context):
    options = context_options(context)
    assert len(set(options)) == len(options)
    assert options[-2:] == (NO_MOVE, CANNOT_TELL)


@pytest.mark.parametrize("context", list(Context))
def test_real_move_options_are_fiction_moves(context: Context):
    for option in context_options(context):
        if option not in SPECIAL_OPTIONS:
            assert move_group(datasworn(), option) is MoveGroup.FICTION


def test_largest_context_fits_ollama_limit():
    assert max(len(context_options(context)) for context in Context) <= 26


EXPLORING = (
    "face_danger",
    "secure_an_advantage",
    "gather_information",
    "heal",
    "resupply",
    "make_camp",
    "undertake_a_journey",
    "compel",
    "sojourn",
    "draw_the_circle",
    "forge_a_bond",
    "test_your_bond",
    "swear_an_iron_vow",
    "fulfill_your_vow",
    "forsake_your_vow",
    "enter_the_fray",
    "battle",
    "write_your_epilogue",
    NO_MOVE,
    CANNOT_TELL,
)


def test_exact_option_order():
    assert context_options(Context.EXPLORING) == EXPLORING
    assert context_options(Context.JOURNEY) == (
        *EXPLORING[:-2],
        "reach_your_destination",
        NO_MOVE,
        CANNOT_TELL,
    )
    assert context_options(Context.FIGHT) == (
        ATTACK,
        "battle",
        "face_danger",
        "secure_an_advantage",
        "gather_information",
        "compel",
        "heal",
        "forsake_your_vow",
        NO_MOVE,
        CANNOT_TELL,
    )


def test_exploring_leaves_out_fight_and_destination_moves():
    options = set(context_options(Context.EXPLORING))
    assert options.isdisjoint({"strike", "clash", "reach_your_destination", ATTACK})
    assert "battle" in options
    assert "enter_the_fray" in options


def test_journey_adds_reach_your_destination():
    exploring = context_options(Context.EXPLORING)
    journey = context_options(Context.JOURNEY)
    assert set(journey) - set(exploring) == {"reach_your_destination"}


def test_attack_is_strike_with_initiative_and_clash_without():
    assert attack_move("character") == "strike"
    assert attack_move("foe") == "clash"


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        (
            Context.EXPLORING,
            ("face_danger", "secure_an_advantage", "compel", "enter_the_fray", "battle"),
        ),
        (
            Context.JOURNEY,
            ("face_danger", "secure_an_advantage", "compel", "enter_the_fray", "battle"),
        ),
        (
            Context.FIGHT,
            (ATTACK, "battle", "face_danger", "secure_an_advantage", "compel"),
        ),
    ],
)
def test_stat_question_options(context: Context, expected: tuple[str, ...]):
    assert stat_question_options(datasworn(), context) == expected


def test_face_danger_stat_choices_come_from_the_move_data():
    choices = stat_choices(datasworn(), "face_danger")
    assert [choice.stat for choice in choices] == ["edge", "heart", "iron", "shadow", "wits"]
    assert choices[0].text == "With speed, agility, or precision"


def test_attack_stat_choices_are_iron_close_and_edge_at_range():
    choices = stat_choices(datasworn(), ATTACK)
    assert [choice.stat for choice in choices] == ["iron", "edge"]
    assert [choice.text for choice in choices] == ["In close quarters", "At range"]


def test_strike_and_clash_offer_the_same_stats():
    strike = [choice.stat for choice in stat_choices(datasworn(), "strike")]
    clash = [choice.stat for choice in stat_choices(datasworn(), "clash")]
    assert strike == clash == ["iron", "edge"]


@pytest.mark.parametrize(
    "move_id", ["heal", "gather_information", "endure_harm", "no_move", "cannot_tell"]
)
def test_moves_without_a_stat_question_have_no_choices(move_id: str):
    assert stat_choices(datasworn(), move_id) == ()


def test_move_group_rejects_unknown_ids():
    with pytest.raises(UnknownIdError):
        move_group(datasworn(), "strik")


def test_stat_choices_rejects_unknown_ids():
    with pytest.raises(UnknownIdError):
        stat_choices(datasworn(), "bogus")


@pytest.mark.parametrize(
    ("option", "initiative", "expected"),
    [
        ("face_danger", None, "face_danger"),
        ("face_danger", "foe", "face_danger"),
        (ATTACK, "character", "strike"),
        (ATTACK, "foe", "clash"),
        (NO_MOVE, None, None),
        (CANNOT_TELL, "character", None),
    ],
)
def test_resolve_option(option: str, initiative: Initiative | None, expected: str | None):
    assert resolve_option(option, initiative) == expected


def test_attack_outside_a_fight_rejected():
    with pytest.raises(ValueError, match="fight"):
        resolve_option(ATTACK, None)


def test_stat_question_id():
    assert stat_question_id("face_danger") == "stat_face_danger"
    assert stat_question_id(ATTACK) == "stat_attack"
