"""The campaign model, character creation, and JSON persistence."""

from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from ironsworn_tui.campaign import (
    Campaign,
    Character,
    Foe,
    ProgressTrack,
    create_character,
    new_campaign,
)
from ironsworn_tui.moves import Context
from ironsworn_tui.rules.datasworn import Stat, datasworn
from ironsworn_tui.rules.errors import UnknownIdError
from ironsworn_tui.rules.progress import Rank

STATS: dict[Stat, int] = {"edge": 2, "heart": 2, "iron": 1, "shadow": 1, "wits": 3}
ASSETS = ["archer", "hawk:2", "wright"]


def kira() -> Character:
    return create_character(datasworn(), "Kira", "a hunter", STATS, ASSETS)


def test_create_character_starts_with_full_meters():
    character = kira()
    assert (character.health, character.spirit, character.supply) == (5, 5, 5)
    assert character.momentum == 2
    assert character.stats.value("wits") == 3


@pytest.mark.parametrize(
    "stats",
    [
        {"edge": 3, "heart": 3, "iron": 1, "shadow": 1, "wits": 1},
        {"edge": 3, "heart": 2, "iron": 2, "shadow": 1},
    ],
)
def test_create_character_rejects_other_stat_arrays(stats: dict[str, int]):
    with pytest.raises(ValueError, match="stats"):
        create_character(datasworn(), "Kira", "a hunter", cast(dict[Stat, int], stats), ASSETS)


def test_create_character_needs_three_real_assets():
    with pytest.raises(ValueError, match="assets"):
        create_character(datasworn(), "Kira", "a hunter", STATS, ["archer"])
    with pytest.raises(UnknownIdError):
        create_character(datasworn(), "Kira", "a hunter", STATS, ["archer", "hawk:2", "laser"])


def test_condition_stops_its_meter_from_increasing():
    character = kira()
    character.health = 2
    character.mark_debility("wounded")
    assert character.change_meter("health", 2) == 0
    assert character.health == 2
    assert character.change_meter("health", -1) == -1
    character.clear_debility("wounded")
    assert character.change_meter("health", 2) == 2


def test_meters_stay_between_0_and_5():
    character = kira()
    assert character.change_meter("supply", 3) == 0
    assert character.change_meter("supply", -7) == -5
    assert character.supply == 0


def test_debilities_lower_max_momentum_and_reset():
    character = kira()
    character.momentum = 10
    character.mark_debility("shaken")
    assert character.momentum == 9
    character.mark_debility("encumbered")
    assert character.bounds.max == 8
    assert character.momentum == 8
    character.reset_momentum()
    assert character.momentum == 0


def test_momentum_loss_past_minimum_is_a_setback():
    character = kira()
    character.momentum = -5
    assert character.change_momentum(-3) == 2
    assert character.momentum == -6


def test_progress_marks_by_rank_and_caps_at_40():
    track = ProgressTrack(name="Find my brother", rank=Rank.DANGEROUS)
    track.mark()
    assert track.ticks == 8
    track.mark(times=5)
    assert track.ticks == 40
    assert track.boxes == 10


def test_recommit_clears_all_but_one_box_and_raises_rank():
    track = ProgressTrack(name="Vow", rank=Rank.FORMIDABLE, ticks=22)
    track.recommit()
    assert (track.ticks, track.rank) == (4, Rank.EXTREME)
    epic = ProgressTrack(name="Vow", rank=Rank.EPIC, ticks=3)
    epic.recommit()
    assert (epic.ticks, epic.rank) == (0, Rank.EPIC)


def test_context_follows_foes_and_journey():
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    assert campaign.context is Context.EXPLORING
    campaign.journey = ProgressTrack(name="Highcairn", rank=Rank.DANGEROUS)
    assert campaign.context is Context.JOURNEY
    campaign.foes.append(Foe(name="Raider", rank=Rank.DANGEROUS))
    assert campaign.context is Context.FIGHT


def test_removing_the_last_foe_ends_the_fight():
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    raider = Foe(name="Raider", rank=Rank.DANGEROUS)
    archer = Foe(name="Archer", rank=Rank.TROUBLESOME)
    campaign.foes = [raider, archer]
    campaign.target = "Raider"
    campaign.initiative = "character"
    campaign.tide_used = True
    campaign.remove_foe(raider)
    assert campaign.target == "Archer"
    assert campaign.initiative == "character"
    campaign.remove_foe(archer)
    assert (campaign.target, campaign.initiative, campaign.tide_used) == (None, None, False)


def test_target_defaults_to_the_first_foe():
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    assert campaign.target_foe() is None
    campaign.foes = [Foe(name="Raider", rank=Rank.DANGEROUS)]
    assert campaign.target_foe() is campaign.foes[0]


def test_save_and_load_round_trip(tmp_path: Path):
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    campaign.foes = [Foe(name="Raider", rank=Rank.DANGEROUS, ticks=8)]
    campaign.initiative = "foe"
    campaign.character.mark_debility("wounded")
    campaign.add_log("message", "I wade across the ford.")
    path = tmp_path / "campaigns" / "kira.json"
    campaign.save(path)
    assert Campaign.load(path) == campaign
    assert '"schema_version": 3' in path.read_text()
    assert not path.with_suffix(".json.tmp").exists()


def test_unknown_fields_are_rejected(tmp_path: Path):
    path = tmp_path / "bad.json"
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    path.write_text(campaign.model_dump_json().replace('"bonds"', '"bondz"'))
    with pytest.raises(ValidationError):
        Campaign.load(path)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"target": "Ghost"}, "target"),
        ({"initiative": None}, "initiative"),
        ({"foes": [Foe(name="Raider", rank=Rank.DANGEROUS)] * 2}, "foes share"),
    ],
)
def test_load_rejects_parts_that_disagree(tmp_path: Path, change: dict[str, object], problem: str):
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    campaign.foes = [Foe(name="Raider", rank=Rank.DANGEROUS)]
    campaign.target = "Raider"
    campaign.initiative = "character"
    broken = campaign.model_copy(update=change)
    path = tmp_path / "broken.json"
    path.write_text(broken.model_dump_json())
    with pytest.raises(ValueError, match=problem):
        Campaign.load(path)


def test_load_rejects_momentum_over_the_maximum(tmp_path: Path):
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    campaign.character.momentum = 10
    campaign.character.debilities = ["wounded"]
    path = tmp_path / "broken.json"
    path.write_text(campaign.model_dump_json())
    with pytest.raises(ValueError, match="momentum"):
        Campaign.load(path)


def test_ending_a_fight_clears_its_state():
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    campaign.foes = [Foe(name="Raider", rank=Rank.DANGEROUS)]
    campaign.initiative = "foe"
    campaign.tide_armed = True
    campaign.end_fight_offered = True
    campaign.end_fight()
    assert campaign.context is Context.EXPLORING
    assert (campaign.initiative, campaign.tide_armed, campaign.end_fight_offered) == (
        None,
        False,
        False,
    )


def test_ending_a_fight_restores_harm_and_foe_harm():
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    campaign.foes = [Foe(name="Rival", rank=Rank.DANGEROUS)]
    campaign.initiative = "character"
    campaign.foe_harm_bonus = 1
    campaign.harm_after_fight = 2
    campaign.character.harm = 1
    campaign.end_fight()
    assert (campaign.character.harm, campaign.foe_harm_bonus, campaign.harm_after_fight) == (
        2,
        0,
        None,
    )
