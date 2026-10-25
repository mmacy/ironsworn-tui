"""The vendored Datasworn data and its indices."""

from typing import Any, cast

import pytest
from pydantic import ValidationError

from ironsworn_tui.rules.datasworn import (
    AssetControlOption,
    ConditionMeterOption,
    Move,
    StatOption,
    YamlMap,
    datasworn,
    plain_text,
)
from ironsworn_tui.rules.errors import UnknownIdError


def test_move_count_matches_rulebook():
    assert len(datasworn().moves) == 35


def test_move_lookup():
    move = datasworn().move("face_danger")
    assert move.id == "face_danger"
    assert move.name == "Face Danger"
    assert move.category == "adventure"
    assert move.roll_type == "action_roll"
    assert move.trigger.text.startswith("When you attempt something risky")


def test_move_outcomes():
    outcomes = datasworn().move("face_danger").outcomes
    assert outcomes is not None
    assert outcomes.strong_hit.text.startswith("On a __strong hit__")
    assert "Pay the Price" in outcomes.miss.text


def test_moves_without_rolls_have_no_outcomes():
    assert datasworn().move("pay_the_price").outcomes is None


@pytest.mark.parametrize(
    ("roll_type", "count"),
    [("action_roll", 22), ("progress_roll", 3), ("special_track", 1), ("no_roll", 9)],
)
def test_roll_types(roll_type: str, count: int):
    assert sum(move.roll_type == roll_type for move in datasworn().moves.values()) == count


def test_conditions_and_roll_options():
    heal = datasworn().move("heal").trigger.conditions
    assert heal[0].method == "player_choice"
    assert heal[0].text is None
    assert heal[0].roll_options == (StatOption(using="stat", stat="wits"),)
    assert heal[1].method == "lowest"
    assert heal[1].text == "Mend your own wounds"
    assert heal[1].roll_options == (
        StatOption(using="stat", stat="iron"),
        StatOption(using="stat", stat="wits"),
    )


def test_condition_meter_roll_options():
    endure_harm = datasworn().move("endure_harm").trigger.conditions[0]
    assert endure_harm.method == "highest"
    assert endure_harm.roll_options == (
        StatOption(using="stat", stat="iron"),
        ConditionMeterOption(using="condition_meter", condition_meter="health"),
    )


def test_asset_control_roll_option():
    options = datasworn().move("companion_endure_harm").trigger.conditions[0].roll_options
    assert options[1] == AssetControlOption(
        using="asset_control", control="health", assets=("asset:*/companion/*",)
    )


@pytest.mark.parametrize(
    ("move_id", "category"),
    [
        ("reach_your_destination", "Journey"),
        ("end_the_fight", "Combat"),
        ("fulfill_your_vow", "Vow"),
    ],
)
def test_progress_moves_name_their_track(move_id: str, category: str):
    tracks = datasworn().move(move_id).tracks
    assert tracks is not None
    assert tracks.category == category


@pytest.mark.parametrize("move_id", sorted(datasworn().moves))
def test_outcomes_exactly_when_the_move_rolls(move_id: str):
    move = datasworn().move(move_id)
    assert (move.outcomes is None) == (move.roll_type == "no_roll")


def _face_danger_fields() -> dict[str, Any]:
    return datasworn().move("face_danger").model_dump()


@pytest.mark.parametrize(
    "change",
    [
        {"roll_type": "dice_roll"},
        {"rollOptions": []},
        {"outcomes": None},
        {"roll_type": "no_roll"},
        {"tracks": {"category": "Vow"}},
        {"trigger": {"text": "When...", "conditions": [{"roll_options": [{"using": "stat"}]}]}},
        {"trigger": {"text": "When...", "conditions": [{"roll_options": [{"using": "luck"}]}]}},
    ],
)
def test_bad_move_data_rejected(change: dict[str, Any]):
    with pytest.raises(ValidationError):
        Move.model_validate({**_face_danger_fields(), **change})


def test_moves_are_frozen():
    move = datasworn().move("face_danger")
    with pytest.raises(ValidationError):
        move.name = "Face Peril"


def test_npc_lookup():
    assert datasworn().npc("warrior")["rank"] == 2


def test_assets_indexed():
    assert len(datasworn().assets) > 0


@pytest.mark.parametrize("kind", ["move", "oracle", "npc", "asset"])
def test_unknown_id_rejected(kind: str):
    data = datasworn()
    lookup = {"move": data.move, "oracle": data.oracle, "npc": data.npc, "asset": data.asset}
    with pytest.raises(UnknownIdError):
        lookup[kind]("nope_not_real")


def test_indices_are_read_only():
    npcs = cast(dict[str, YamlMap], datasworn().npcs)
    moves = cast(dict[str, Move], datasworn().moves)
    with pytest.raises(TypeError):
        npcs["warrior"] = {}
    with pytest.raises(TypeError):
        moves["face_danger"] = datasworn().move("strike")


def test_plain_text_drops_links_and_bold_markers():
    text = (
        "On a __weak hit__, make the [Endure Harm](datasworn:move:classic/suffer/endure_harm) move."
    )
    assert plain_text(text) == "On a weak hit, make the Endure Harm move."


def test_plain_text_drops_table_templates():
    text = "Roll on the following table.\n\n{{table>move.oracle_rollable:classic/suffer/x.x}}"
    assert plain_text(text) == "Roll on the following table."
