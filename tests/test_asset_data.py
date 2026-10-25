"""The typed asset models over the Datasworn assets."""

import pytest
from pydantic import ValidationError

from ironsworn_tui.rules.datasworn import (
    AssetControlOption,
    AssetOptionRoll,
    StatOption,
    datasworn,
)


def test_every_asset_loads_with_three_abilities():
    assets = datasworn().assets
    assert len(assets) == 78
    assert all(len(asset.abilities) == 3 for asset in assets.values())
    categories = {asset.category for asset in assets.values()}
    assert categories == {"Combat Talent", "Companion", "Path", "Ritual"}


def test_asset_fields():
    archer = datasworn().asset("archer")
    assert archer.name == "Archer"
    assert archer.requirement == "If you wield a bow..."
    assert [ability.enabled for ability in archer.abilities] == [True, False, False]
    assert archer.abilities[1].text.startswith("Once per fight, when you Strike or Clash")


def test_ability_text_is_plain():
    # The `datasworn:` links become their labels, so the text reads well in the panel.
    text = datasworn().asset("berserker").abilities[1].text
    assert "datasworn:" not in text
    assert "Endure Harm (1 harm)" in text


def test_companion_has_a_health_meter_and_a_name():
    hawk = datasworn().asset("hawk")
    assert hawk.meters["health"].max == 3
    assert hawk.meters["health"].value == 3
    assert hawk.texts == ("name",)
    assert not any(ability.enabled for ability in hawk.abilities)


def test_meters_that_start_empty():
    assert datasworn().asset("fortune_hunter").meters["wealth"].value == 0
    assert datasworn().asset("invoke").meters["essence"].max == 6


def test_select_fields():
    devotant = datasworn().asset("devotant")
    assert devotant.texts == ("gods_name",)
    assert devotant.selects["stat"].choices["wits"].stat == "wits"
    masked = datasworn().asset("masked")
    assert masked.selects["material"].choices["ghostwood"].stat == "shadow"
    ironclad = datasworn().asset("ironclad")
    assert ironclad.selects["equipped"].choices["geared_for_war"].counts_as_debility
    assert not ironclad.selects["equipped"].choices["lightly_armored"].counts_as_debility


def test_oathbreaker_counts_as_a_debility():
    assert datasworn().asset("oathbreaker").counts_as_debility
    assert not datasworn().asset("archer").counts_as_debility


def test_enhancement_names_the_moves_it_enhances():
    archer = datasworn().asset("archer")
    first = archer.abilities[0].enhancements[0]
    assert first.moves == ("secure_an_advantage",)
    assert first.roll_options == (StatOption(using="stat", stat="wits"),)
    assert archer.abilities[1].enhancements[0].moves == ("strike", "clash")
    assert archer.abilities[2].enhancements[0].roll_options == ()


def test_enhancement_with_no_moves_enhances_any_move():
    kindred = datasworn().asset("kindred")
    assert kindred.abilities[0].enhancements[0].moves is None


def test_roll_with_an_asset_meter_or_option():
    commander = datasworn().asset("commander")
    options = commander.abilities[0].enhancements[0].roll_options
    assert AssetControlOption(using="asset_control", control="strength") in options
    devotant = datasworn().asset("devotant")
    roll = devotant.abilities[0].enhancements[0].roll_options
    assert roll == (AssetOptionRoll(using="asset_option", option="stat"),)


def test_ritual_adds_its_move():
    augur = datasworn().asset("augur")
    move = augur.abilities[0].moves[0]
    assert (move.id, move.name, move.category) == ("augur", "Augur", "asset")
    assert move.outcomes is not None
    assert augur.abilities[2].enhancements[0].moves == ("augur",)


def test_asset_moves_are_indexed_with_their_asset():
    data = datasworn()
    assert data.asset_move("augur").name == "Augur"
    assert data.asset_for_move("augur") == "augur"
    assert data.asset_for_move("craft_arrow") == "fletcher"
    assert len(data.asset_moves) == 23
    # Asset moves don't join the core moves, which the model's questions are built from.
    assert "augur" not in data.moves


def test_awakening_raises_its_meter():
    awakening = datasworn().asset("awakening")
    assert awakening.meters["health"].max == 3
    assert awakening.abilities[1].meter_max == {"health": 6}


def test_assets_are_frozen():
    with pytest.raises(ValidationError):
        datasworn().asset("archer").name = "Bowman"
