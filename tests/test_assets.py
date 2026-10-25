"""Owning assets: buying, upgrading, meters, fields, and one-time changes."""

from collections.abc import Callable
from pathlib import Path

import pytest

from ironsworn_tui.assets import (
    buy,
    change_asset_meter,
    discard,
    set_debility,
    set_field,
    upgrade,
)
from ironsworn_tui.campaign import (
    AssetError,
    Campaign,
    Character,
    create_character,
    new_campaign,
    new_owned,
)
from ironsworn_tui.rules.datasworn import Stat, datasworn
from ironsworn_tui.rules.progress import Rank

STATS: dict[Stat, int] = {"edge": 2, "heart": 2, "iron": 1, "shadow": 1, "wits": 3}


def kira(experience: int = 10) -> Character:
    character = create_character(
        datasworn(), "Kira", "a hunter", STATS, ["archer", "hawk:2", "wright"]
    )
    character.experience = experience
    return character


def test_starting_assets_mark_their_enabled_abilities():
    character = kira()
    archer, hawk, wright = character.assets
    assert archer.marked == [True, False, False]
    assert hawk.marked == [False, True, False]
    assert hawk.meters == {"health": 3}
    assert wright.fields == {}


def test_asset_without_an_enabled_ability_needs_a_pick():
    with pytest.raises(AssetError, match="pick"):
        new_owned(datasworn(), "hawk", None)
    with pytest.raises(AssetError, match="already"):
        new_owned(datasworn(), "archer", 1)
    with pytest.raises(AssetError, match="1 to 3"):
        new_owned(datasworn(), "hawk", 4)


def test_create_character_rejects_a_bad_pick():
    with pytest.raises(AssetError):
        create_character(datasworn(), "Kira", "a hunter", STATS, ["archer", "hawk", "wright"])


def test_buy_spends_three_experience():
    character = kira(experience=4)
    assert buy(character, datasworn(), "slayer") == 3
    assert character.experience == 1
    assert character.asset("slayer").marked == [True, False, False]


def test_buy_needs_enough_experience_and_a_new_asset():
    character = kira(experience=2)
    with pytest.raises(AssetError, match="experience"):
        buy(character, datasworn(), "slayer")
    character.experience = 5
    with pytest.raises(AssetError, match="already"):
        buy(character, datasworn(), "archer")
    assert character.experience == 5


def test_upgrade_spends_two_experience():
    character = kira(experience=2)
    assert upgrade(character, datasworn(), "archer", 2) == 2
    assert character.asset("archer").marked == [True, True, False]
    assert character.experience == 0
    with pytest.raises(AssetError, match="experience"):
        upgrade(character, datasworn(), "archer", 3)
    character.experience = 2
    with pytest.raises(AssetError, match="already"):
        upgrade(character, datasworn(), "archer", 2)
    with pytest.raises(AssetError, match="own"):
        upgrade(character, datasworn(), "slayer", 2)


def test_animal_kin_makes_companions_cheaper():
    character = kira(experience=10)
    buy(character, datasworn(), "animal_kin")
    upgrade(character, datasworn(), "animal_kin", 2)
    assert character.experience == 5
    assert buy(character, datasworn(), "owl", 1) == 2
    assert upgrade(character, datasworn(), "hawk", 1) == 1
    assert upgrade(character, datasworn(), "archer", 2) == 2


@pytest.mark.parametrize(
    ("path", "ability", "kind"),
    [("ritualist", 3, "augur"), ("weaponmaster", 2, "duelist")],
)
def test_paths_that_make_their_kind_cheaper(path: str, ability: int, kind: str):
    character = kira(experience=20)
    character.assets.append(new_owned(datasworn(), path, None))
    character.asset(path).marked[ability - 1] = True
    assert buy(character, datasworn(), kind) == 2
    assert upgrade(character, datasworn(), kind, 2) == 1


def test_shadow_kin_moves_stat_points():
    character = kira()
    character.stats.heart = 2
    buy(character, datasworn(), "shadow_kin", 1, {"heart": -1, "shadow": 2})
    assert (character.stats.heart, character.stats.shadow) == (1, 3)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"heart": -1, "shadow": 3},
        {"heart": -1, "wits": 1},
        {"shadow": 1},
    ],
)
def test_shadow_kin_rejects_other_changes(changes: dict[Stat, int]):
    character = kira()
    with pytest.raises(AssetError, match=r"(?i)shadow-kin"):
        buy(character, datasworn(), "shadow_kin", 1, changes)
    assert character.asset_or_none("shadow_kin") is None
    assert character.experience == 10


def test_shadow_kin_stops_at_four():
    character = kira()
    character.stats.shadow = 3
    with pytest.raises(AssetError, match="4"):
        buy(character, datasworn(), "shadow_kin", 1, {"heart": -1, "shadow": 2})
    buy(character, datasworn(), "shadow_kin", 1, {"heart": -1, "shadow": 1})
    assert character.stats.shadow == 4


@pytest.mark.parametrize(
    ("changes", "after"),
    [
        ({"iron": -1, "wits": 1, "heart": 1}, (2, 0, 4, 3)),
        ({"edge": -1, "heart": 2}, (1, 1, 3, 4)),
    ],
)
def test_battle_scarred_focus(changes: dict[Stat, int], after: tuple[int, int, int, int]):
    character = kira()
    buy(character, datasworn(), "battle_scarred", 1, changes)
    s = character.stats
    assert (s.edge, s.iron, s.wits, s.heart) == after


def test_battle_scarred_focus_rejects_other_changes():
    character = kira()
    with pytest.raises(AssetError, match=r"(?i)battle-scarred"):
        buy(character, datasworn(), "battle_scarred", 1, {"heart": -1, "wits": 2})
    with pytest.raises(AssetError, match="4"):
        buy(character, datasworn(), "battle_scarred", 1, {"iron": -1, "wits": 2})


def test_other_abilities_take_no_stat_changes():
    character = kira()
    with pytest.raises(AssetError, match="stat"):
        upgrade(character, datasworn(), "archer", 2, {"wits": 1})


def test_battle_scarred_overcome_lowers_max_health_and_ignores_maimed():
    character = kira()
    character.mark_debility("maimed")
    assert character.bounds.max == 9
    buy(character, datasworn(), "battle_scarred", 2)
    assert character.health_max == 4
    assert character.health == 4
    assert character.bounds.max == 10
    assert character.change_meter("health", 3) == 0


def test_oathbreaker_counts_as_a_debility():
    character = kira()
    buy(character, datasworn(), "oathbreaker")
    assert character.bounds.max == 9


def test_commander_at_zero_strength_counts_as_a_debility():
    character = kira()
    buy(character, datasworn(), "commander")
    assert character.asset("commander").meters == {"strength": 4}
    assert change_asset_meter(character, datasworn(), "commander", "strength", -5) == -4
    assert character.bounds.max == 9
    change_asset_meter(character, datasworn(), "commander", "strength", 1)
    assert character.bounds.max == 10


def test_asset_meter_stays_in_range():
    character = kira()
    assert change_asset_meter(character, datasworn(), "hawk", "health", 2) == 0
    assert change_asset_meter(character, datasworn(), "hawk", "health", -2) == -2
    with pytest.raises(AssetError, match="meter"):
        change_asset_meter(character, datasworn(), "hawk", "strength", 1)


def test_awakening_raises_its_meter_max():
    character = kira()
    buy(character, datasworn(), "awakening")
    change_asset_meter(character, datasworn(), "awakening", "health", 5)
    assert character.asset("awakening").meters["health"] == 3
    upgrade(character, datasworn(), "awakening", 2)
    change_asset_meter(character, datasworn(), "awakening", "health", 5)
    assert character.asset("awakening").meters["health"] == 6


def test_text_and_select_fields():
    character = kira()
    set_field(character, datasworn(), "hawk", "name", "Kestrel")
    assert character.asset("hawk").fields == {"name": "Kestrel"}
    buy(character, datasworn(), "devotant")
    set_field(character, datasworn(), "devotant", "stat", "heart")
    assert character.asset("devotant").fields["stat"] == "heart"
    with pytest.raises(AssetError, match="edge, heart"):
        set_field(character, datasworn(), "devotant", "stat", "charm")
    with pytest.raises(AssetError, match="field"):
        set_field(character, datasworn(), "hawk", "colour", "red")


def test_ironclad_geared_for_war_marks_encumbered():
    character = kira()
    buy(character, datasworn(), "ironclad")
    set_field(character, datasworn(), "ironclad", "equipped", "geared_for_war")
    assert "encumbered" in character.debilities
    set_field(character, datasworn(), "ironclad", "equipped", "lightly_armored")
    assert "encumbered" not in character.debilities


def test_discard():
    character = kira()
    discard(character, "hawk")
    assert [asset.id for asset in character.assets] == ["archer", "wright"]
    with pytest.raises(AssetError, match="own"):
        discard(character, "hawk")


def test_owned_assets_save_and_load(tmp_path: Path):
    character = kira()
    set_field(character, datasworn(), "hawk", "name", "Kestrel")
    change_asset_meter(character, datasworn(), "hawk", "health", -1)
    campaign = new_campaign(character, "Avenge my village", Rank.EPIC)
    path = tmp_path / "kira.json"
    campaign.save(path)
    loaded = Campaign.load(path)
    assert loaded.character.assets == character.assets


def test_load_rejects_a_meter_over_its_max(tmp_path: Path):
    campaign: Campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    campaign.character.asset("hawk").meters["health"] = 9
    with pytest.raises(ValueError, match="health"):
        campaign.check()


def test_new_character_with_battle_scarred_overcome_loads(tmp_path: Path):
    character = create_character(
        datasworn(), "Kira", "a hunter", STATS, ["archer", "battle_scarred:2", "wright"]
    )
    assert character.health == 4
    campaign = new_campaign(character, "Avenge my village", Rank.EPIC)
    campaign.save(tmp_path / "kira.json")
    Campaign.load(tmp_path / "kira.json")


def test_discarding_battle_scarred_lowers_momentum_to_the_new_max():
    character = kira()
    buy(character, datasworn(), "battle_scarred", 2)
    character.mark_debility("maimed")
    character.momentum = 10
    discard(character, "battle_scarred")
    assert character.momentum == 9


def test_animal_kin_doesnt_discount_kindred():
    character = kira(experience=10)
    character.assets.append(new_owned(datasworn(), "animal_kin", None))
    character.asset("animal_kin").marked[1] = True
    assert buy(character, datasworn(), "kindred", 1) == 3


def test_kindred_has_an_expertise_field():
    character = kira()
    buy(character, datasworn(), "kindred", 1)
    set_field(character, datasworn(), "kindred", "expertise", "healer")
    assert character.asset("kindred").fields["expertise"] == "healer"


def test_lightly_armored_keeps_encumbered_from_elsewhere():
    character = kira()
    character.mark_debility("encumbered")
    buy(character, datasworn(), "ironclad")
    set_field(character, datasworn(), "ironclad", "equipped", "lightly_armored")
    assert "encumbered" in character.debilities


def test_asset_debility_can_be_set_by_hand():
    character = kira()
    set_debility(character, "hawk", on=True)
    assert character.bounds.max == 9
    set_debility(character, "hawk", on=False)
    assert character.bounds.max == 10


def test_shadow_kin_can_add_nothing_when_shadow_is_four():
    character = kira()
    character.stats.shadow = 4
    buy(character, datasworn(), "shadow_kin", 1, {"heart": -1})
    assert character.stats.shadow == 4


def _unmark_archer(character: Character) -> None:
    character.asset("archer").marked[0] = False


def _unmark_hawk(character: Character) -> None:
    character.asset("hawk").marked[1] = False


def _oathbreaker_without_debility(character: Character) -> None:
    character.assets[0].id = "oathbreaker"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_unmark_archer, "archer"),
        (_unmark_hawk, "hawk"),
        (_oathbreaker_without_debility, "oathbreaker"),
    ],
)
def test_load_rejects_bad_marks_and_debility(change: Callable[[Character], None], message: str):
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    change(campaign.character)
    with pytest.raises(ValueError, match=message):
        campaign.check()


def test_load_rejects_geared_for_war_without_encumbered():
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    buy(campaign.character, datasworn(), "ironclad")
    campaign.character.asset("ironclad").fields["equipped"] = "geared_for_war"
    with pytest.raises(ValueError, match="encumbered"):
        campaign.check()
