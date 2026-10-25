"""The vendored Datasworn data and its indices."""

from typing import cast

import pytest

from ironsworn_tui.rules.datasworn import YamlMap, datasworn
from ironsworn_tui.rules.errors import UnknownIdError


def test_move_count_matches_rulebook():
    assert len(datasworn().moves) == 35


def test_every_move_has_a_category():
    data = datasworn()
    assert set(data.move_categories) == set(data.moves)
    assert data.move_categories["face_danger"] == "adventure"


def test_move_lookup():
    move = datasworn().move("face_danger")
    assert move["name"] == "Face Danger"
    assert move["roll_type"] == "action_roll"


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
    moves = cast(dict[str, YamlMap], datasworn().moves)
    with pytest.raises(TypeError):
        moves["face_danger"] = {}
