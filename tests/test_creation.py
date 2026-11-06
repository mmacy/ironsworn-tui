"""Campaign setup: the walkthrough's answers, the campaign they start, and the oracle rolls."""

import random
from pathlib import Path

import pytest

from ironsworn_tui.campaign import AssetError, WorldTruth
from ironsworn_tui.creation import (
    AssetPick,
    Setup,
    begin_campaign,
    needs_ability,
    open_play,
    pickable_abilities,
    quest_starters,
    roll_name,
    roll_place_name,
    roll_spark,
    roll_truth,
)
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import TurnEngine
from tests.support import STATS, THRESHOLDS, Dice


def blarg(**changes: object) -> Setup:
    setup = Setup(
        name="Blarg",
        description="the Destructor",
        stats=dict(STATS),
        assets=[
            AssetPick("archer"),
            AssetPick("wayfinder"),
            AssetPick("hawk", ability=1, fields={"name": "Kestrel"}),
        ],
        truths={"iron": 0, "mysticism": 1},
        region="havens",
        place="Cinderhome",
        bonds=["My village", "Oda the overseer"],
        background_vow="Find who burned my village",
        inciting_incident="The overseer is sick, and no healer can help her.",
        scene="The overseer's longhouse at night",
        vow="Find a cure for the overseer",
    )
    for key, value in changes.items():
        setattr(setup, key, value)
    return setup


def test_begin_campaign_makes_the_character():
    campaign = begin_campaign(datasworn(), blarg())
    character = campaign.character
    assert (character.name, character.description) == ("Blarg", "the Destructor")
    assert character.stats.wits == 3
    assert [owned.id for owned in character.assets] == ["archer", "wayfinder", "hawk"]
    hawk = character.asset("hawk")
    assert hawk.marked == [True, False, False]
    assert hawk.fields == {"name": "Kestrel"}
    assert character.harm == 2


def test_begin_campaign_records_bonds_and_the_background_vow():
    campaign = begin_campaign(datasworn(), blarg(background_rank=Rank.EXTREME))
    assert campaign.bonds == 2
    assert campaign.background_vow == "Find who burned my village"
    assert [(vow.name, vow.rank) for vow in campaign.vows] == [
        ("Find who burned my village", Rank.EXTREME)
    ]


def test_begin_campaign_records_the_world_and_the_scene():
    campaign = begin_campaign(datasworn(), blarg())
    world = campaign.world
    iron = datasworn().truths["iron"].options[0].description
    rare = datasworn().truths["mysticism"].options[1].description
    assert world.truths == [
        WorldTruth(name="Iron", text=iron),
        WorldTruth(name="Mysticism", text=rare),
    ]
    assert (world.region, world.place) == ("Havens", "Cinderhome")
    assert world.inciting_incident == "The overseer is sick, and no healer can help her."
    assert campaign.situation == "The overseer's longhouse at night"
    texts = [entry.text for entry in campaign.log]
    assert "Inciting incident: The overseer is sick, and no healer can help her." in texts
    assert "Scene: The overseer's longhouse at night" in texts


def test_truths_keep_the_rulebook_order_whatever_order_they_were_picked():
    campaign = begin_campaign(datasworn(), blarg(truths={"horrors": 2, "old_world": 0}))
    assert [truth.name for truth in campaign.world.truths] == ["The Old World", "Horrors"]


def test_begin_campaign_sets_a_select_field():
    setup = blarg(assets=[AssetPick("archer"), AssetPick("wayfinder"), AssetPick("ironclad")])
    setup.assets[2].fields = {"equipped": "geared_for_war"}
    character = begin_campaign(datasworn(), setup).character
    assert character.asset("ironclad").fields == {"equipped": "geared_for_war"}
    # Geared for war marks encumbered, as the asset says.
    assert "encumbered" in character.debilities


def test_begin_campaign_without_a_deadly_weapon():
    assert begin_campaign(datasworn(), blarg(harm=1)).character.harm == 1


def test_begin_campaign_refuses_a_bad_setup():
    with pytest.raises(ValueError, match="3, 2, 2, 1"):
        begin_campaign(datasworn(), blarg(stats={**STATS, "iron": 3}))
    with pytest.raises(AssetError):
        begin_campaign(
            datasworn(),
            blarg(assets=[AssetPick("archer"), AssetPick("wayfinder"), AssetPick("hawk")]),
        )


def test_needs_ability_for_an_asset_with_none_marked():
    assert needs_ability(datasworn(), "hawk")
    assert not needs_ability(datasworn(), "archer")


def test_pickable_abilities_leave_out_those_that_change_stats():
    assert pickable_abilities(datasworn(), "hawk") == (1, 2, 3)
    assert pickable_abilities(datasworn(), "shadow_kin") == (2, 3)


def test_roll_truth_picks_the_option_the_roll_covers():
    dice = Dice()
    dice.load(50)
    assert roll_truth(datasworn(), "iron", dice) == (50, 1)


def test_roll_name_uses_one_of_the_two_name_tables():
    dice = Dice()
    dice.load(2, 1)
    name = roll_name(datasworn(), dice)
    assert name == datasworn().oracle("classic/name/ironlander/b").rows[0].text


def test_roll_place_name_joins_a_prefix_and_a_suffix():
    data = datasworn()
    dice = Dice()
    dice.load(1, 1)
    prefix = data.oracle("classic/settlement/quick_name/prefix").rows[0].text
    suffix = data.oracle("classic/settlement/quick_name/suffix").rows[0].text
    assert roll_place_name(data, dice) == prefix + suffix


def test_roll_spark_pairs_an_action_and_a_theme():
    data = datasworn()
    dice = Dice()
    dice.load(1, 1)
    action = data.oracle("classic/action_and_theme/action").rows[0].text
    theme = data.oracle("classic/action_and_theme/theme").rows[0].text
    assert roll_spark(data, dice) == f"{action} and {theme}"


def test_quest_starters_come_from_the_chosen_truths_and_region():
    data = datasworn()
    starters = quest_starters(data, blarg())
    assert starters == [
        ("Iron", data.truths["iron"].options[0].quest_starter),
        ("Mysticism", data.truths["mysticism"].options[1].quest_starter),
        ("Havens", data.regions["havens"].quest_starter),
    ]


def _engine(setup: Setup, tmp_path: Path) -> tuple[TurnEngine, Dice]:
    dice = Dice()
    campaign = begin_campaign(datasworn(), setup)
    path = tmp_path / "Blarg.json"
    return TurnEngine(campaign, datasworn(), dice, THRESHOLDS, path=path), dice


def test_open_play_in_media_res_swears_the_vow(tmp_path: Path):
    engine, dice = _engine(blarg(vow_rank=Rank.FORMIDABLE), tmp_path)
    dice.load(5, 2, 3)
    open_play(engine, blarg(vow_rank=Rank.FORMIDABLE))
    assert engine.card is not None
    assert engine.card.move == "swear_an_iron_vow"
    # The card waits in the saved file, so quitting before the roll keeps it.
    assert engine.campaign.pending_card is not None
    assert (tmp_path / "Blarg.json").exists()


def test_open_play_in_a_prologue_waits_for_the_vow(tmp_path: Path):
    setup = blarg(start="prologue", vow="")
    engine, _ = _engine(setup, tmp_path)
    open_play(engine, setup)
    assert engine.card is None
    assert "/vow swear" in engine.campaign.log[-1].text
    assert (tmp_path / "Blarg.json").exists()


def test_rolls_use_the_random_source():
    data = datasworn()
    first = roll_name(data, random.Random(7))
    assert first == roll_name(data, random.Random(7))
