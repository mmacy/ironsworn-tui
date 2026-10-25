"""Asset abilities on a roll: the turn engine applying boosts."""

from pathlib import Path

import pytest

from ironsworn_tui.abilities import BoostRef
from ironsworn_tui.assets import buy, set_field, upgrade
from ironsworn_tui.campaign import Campaign, OwedMove, ProgressTrack
from ironsworn_tui.outcomes import (
    Choose,
    FollowUp,
    GainExperience,
    MaskTrack,
    MeterChange,
    Momentum,
    SetInitiative,
)
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.dice import Hit
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, TurnEngine, TurnError
from tests.support import Dice, engine

TRUST = BoostRef("archer", 1, 0)
LINE_UP = BoostRef("archer", 1, 1)
EXTRA_SHOTS = BoostRef("archer", 2)


def fight(turn: TurnEngine, dice: Dice) -> None:
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()


def give(turn: TurnEngine, asset: str, *abilities: int) -> None:
    """Give Kira an asset with the abilities marked, without spending experience."""
    character = turn.campaign.character
    character.experience += 3 + 2 * len(abilities)
    first = abilities[0] if abilities else None
    owned = character.asset_or_none(asset)
    if owned is None:
        data = datasworn().asset(asset)
        pick = first if not any(a.enabled for a in data.abilities) else None
        buy(character, datasworn(), asset, pick)
    for number in abilities:
        if not character.asset(asset).marked[number - 1]:
            upgrade(character, datasworn(), asset, number)
    character.experience = 0


def test_boosts_for_a_move(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    labels = [available.label for available in turn.boosts_for("secure_an_advantage")]
    assert labels == [
        "Archer 1: Trust your instincts",
        "Archer 1: Line up your shot",
        "Hawk 2: Harass and distract",
        "Wright 1: Craft with your specialty",
    ]
    assert turn.boosts_for("heal") == ()


def test_unmarked_abilities_offer_no_boosts(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert not any(a.ref.asset == "archer" for a in turn.boosts_for("resupply"))
    give(turn, "archer", 3)
    assert [a.label for a in turn.boosts_for("resupply")] == ["Archer 3: Hunting"]


def test_a_boost_changes_the_stat_and_adds(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(4, 7, 9)
    card = turn.make_move("secure_an_advantage", stat="edge", boosts=[TRUST])
    assert card is not None
    assert card.rolled_with == "wits"
    assert card.action is not None
    assert (card.action.value, card.action.adds, card.action.score) == (3, 1, 8)
    assert card.hit is Hit.WEAK
    assert card.boosts == ("Archer 1: Trust your instincts",)
    assert "Archer 1: Trust your instincts" in turn.campaign.log[-1].text


def test_momentum_on_a_strong_hit(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(5, 1, 2)
    card = turn.make_move("secure_an_advantage", stat="edge", boosts=[TRUST])
    assert card is not None
    assert card.effects[-1] == Momentum(2)
    turn.resolve([[1]])
    assert turn.campaign.character.momentum == 6


def test_momentum_on_a_hit(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(4, 6, 9)
    card = turn.make_move("secure_an_advantage", boosts=[LINE_UP])
    assert card is not None
    assert card.rolled_with == "edge"
    assert card.effects == (Momentum(1), Momentum(1))


def test_two_variants_of_one_ability_are_refused(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(TurnError, match="one"):
        turn.make_move("secure_an_advantage", boosts=[TRUST, LINE_UP])


def test_two_stat_changes_are_refused(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(TurnError, match="roll"):
        turn.make_move("secure_an_advantage", boosts=[TRUST, BoostRef("hawk", 2)])


@pytest.mark.parametrize(
    ("ref", "message"),
    [
        (BoostRef("archer", 3), "marked"),
        (BoostRef("slayer", 1), "own"),
        (BoostRef("archer", 1, 5), "variant"),
        (BoostRef("hawk", 2), "Secure an Advantage"),
    ],
)
def test_boosts_that_dont_apply_are_refused(tmp_path: Path, ref: BoostRef, message: str):
    turn, _, _ = engine(tmp_path)
    before = turn.campaign.model_copy(deep=True)
    with pytest.raises(TurnError, match=message):
        turn.make_move("face_danger", stat="edge", boosts=[ref])
    assert turn.campaign == before


def test_cost_reroll_harm_and_once_per_fight(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "archer", 2)
    fight(turn, dice)
    dice.load(1, 9, 10)
    card = turn.make_move("attack", stat="iron", boosts=[EXTRA_SHOTS])
    assert card is not None
    assert turn.campaign.character.supply == 4
    assert card.hit is Hit.MISS
    assert card.can_reroll
    dice.load(6, 1)
    card = turn.reroll([0, 1])
    assert card.action is not None
    assert (card.action.action_die, card.action.challenge_dice) == (6, (1, 10))
    assert card.hit is Hit.WEAK
    assert not card.can_reroll
    turn.resolve()
    # A weak hit on Strike inflicts harm 2, plus 2 for the extra shots.
    assert turn.campaign.foes[0].ticks == 4 * 8
    assert turn.campaign.character.momentum == 2 + 2 + 1
    with pytest.raises(TurnError, match="once per fight"):
        turn.make_move("attack", stat="iron", boosts=[EXTRA_SHOTS])


def test_once_per_fight_resets_after_the_fight(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "archer", 2)
    fight(turn, dice)
    dice.load(6, 1, 1)
    turn.make_move("attack", stat="iron", boosts=[EXTRA_SHOTS])
    turn.resolve()
    turn.end_fight("fled")
    fight(turn, dice)
    assert any(a.ref == EXTRA_SHOTS for a in turn.boosts_for("attack"))


def test_weak_hit_counts_as_a_miss(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "duelist")
    fight(turn, dice)
    dice.load(3, 4, 9)
    card = turn.make_move("attack", stat="iron", boosts=[BoostRef("duelist", 1)])
    assert card is not None
    assert card.action is not None
    assert card.action.hit is Hit.WEAK
    assert card.hit is Hit.MISS


def test_burning_after_a_downgrade_uses_the_downgrade(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "duelist")
    fight(turn, dice)
    turn.campaign.character.momentum = 7
    dice.load(1, 4, 9)
    card = turn.make_move("attack", stat="iron", boosts=[BoostRef("duelist", 1)])
    assert card is not None
    card = turn.burn()
    assert card.hit is Hit.MISS


def test_swordmaster_burn_adds_harm_and_next_move(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "swordmaster")
    fight(turn, dice)
    turn.campaign.character.momentum = 8
    dice.load(1, 6, 7)
    turn.make_move("attack", stat="iron", boosts=[BoostRef("swordmaster", 1)])
    turn.burn()
    turn.resolve()
    # A strong hit on Strike inflicts harm + 1, plus 2 for the sword.
    assert turn.campaign.foes[0].ticks == 8 * 5
    assert turn.campaign.next_add == 1


def test_late_add_with_its_cost(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "wright", 2)
    dice.load(3, 5, 9)
    card = turn.make_move("face_danger", stat="edge", boosts=[BoostRef("wright", 2)])
    assert card is not None
    assert card.hit is Hit.MISS
    assert card.can_late_add
    card = turn.late_add()
    assert card.hit is Hit.WEAK
    assert not card.can_late_add
    assert MeterChange("supply", -1) in card.effects


def test_endure_harm_with_a_boost(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "ironclad")
    set_field(turn.campaign.character, datasworn(), "ironclad", "equipped", "lightly_armored")
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=1))
    dice.load(3, 7, 9)
    card = turn.roll_follow_up(boosts=[BoostRef("ironclad", 1, 0)])
    assert card is not None
    assert card.action is not None
    assert (card.action.value, card.action.adds) == (4, 1)
    assert card.hit is Hit.WEAK
    assert card.effects[-1] == Momentum(1)


def test_armor_boost_needs_the_armor(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    give(turn, "ironclad")
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=1))
    with pytest.raises(TurnError, match="geared for war"):
        turn.roll_follow_up(boosts=[BoostRef("ironclad", 1, 1)])


def test_sacrificing_the_shield_skips_endure_harm(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "shield_bearer", 3)
    fight(turn, dice)
    turn.campaign.initiative = "foe"
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=3))
    assert turn.roll_follow_up(boosts=[BoostRef("shield_bearer", 3)]) is None
    assert turn.campaign.character.health == 5
    assert turn.campaign.initiative == "character"
    assert turn.follow_ups == ()


def test_automatic_strong_hit(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    give(turn, "animal_kin", 2)
    card = turn.make_move("forge_a_bond", boosts=[BoostRef("animal_kin", 2)])
    assert card is not None
    assert card.hit is Hit.STRONG
    assert card.action is None
    turn.resolve([[0]])
    assert turn.campaign.bonds == 2
    assert turn.campaign.character.experience == 1


def test_experience_on_fulfill(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "slayer", 2)
    vow = turn.campaign.vows[0]
    vow.ticks = 40
    dice.load(1, 1)
    card = turn.make_move("fulfill_your_vow", boosts=[BoostRef("slayer", 2, 1)])
    assert card is not None
    assert GainExperience(1) in card.effects
    turn.resolve()
    assert turn.campaign.character.experience == 5 + 1


def test_roll_an_asset_meter(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "commander")
    dice.load(1, 4, 9)
    card = turn.make_move("compel", stat="heart", boosts=[BoostRef("commander", 1, 0)])
    assert card is not None
    assert card.rolled_with == "strength"
    assert card.action is not None
    assert card.action.value == 4


def test_roll_a_field_stat_needs_the_field(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "devotant")
    with pytest.raises(TurnError, match="stat"):
        turn.make_move("secure_an_advantage", boosts=[BoostRef("devotant", 1)])
    set_field(turn.campaign.character, datasworn(), "devotant", "stat", "wits")
    dice.load(1, 4, 9)
    card = turn.make_move("secure_an_advantage", boosts=[BoostRef("devotant", 1)])
    assert card is not None
    assert card.rolled_with == "wits"


def test_mask_applies_only_to_its_stat_and_costs_on_a_one(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "masked")
    set_field(turn.campaign.character, datasworn(), "masked", "material", "whisperwood")
    with pytest.raises(TurnError, match="wits"):
        turn.make_move("face_danger", stat="edge", boosts=[BoostRef("masked", 1)])
    dice.load(1, 9, 10)
    card = turn.make_move("face_danger", stat="wits", boosts=[BoostRef("masked", 1)])
    assert card is not None
    assert MaskTrack(-1) in card.effects
    turn.resolve()
    assert turn.campaign.character.spirit == 4


def test_extra_options_on_a_chosen_outcome(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "cave_lion", 3)
    dice.load(4, 1, 9)
    card = turn.make_move("make_camp", boosts=[BoostRef("cave_lion", 3)])
    assert card is not None
    turn.campaign.character.spirit = 3
    turn.resolve([[2]])
    assert turn.campaign.character.spirit == 5


def test_extra_choice(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "wildblood", 3)
    dice.load(4, 1, 9)
    card = turn.make_move("make_camp", boosts=[BoostRef("wildblood", 3)])
    assert card is not None
    assert card.rolled_with == "wits"
    choose = card.effects[0]
    assert isinstance(choose, Choose)
    assert (choose.count, choose.minimum) == (2, 2)


def test_unleash_light(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "lightbearer", 2)
    character = turn.campaign.character
    character.asset("lightbearer").meters["light"] = 5
    fight(turn, dice)
    with pytest.raises(TurnError, match="light"):
        turn.make_move("attack", boosts=[BoostRef("lightbearer", 2)])
    dice.load(1, 4, 9)
    card = turn.make_move(
        "attack", inputs=MoveInputs(amount=3), boosts=[BoostRef("lightbearer", 2)]
    )
    assert card is not None
    assert card.action is not None
    assert card.action.value == 5
    assert character.asset("lightbearer").meters["light"] == 2
    turn.resolve()
    # A weak hit inflicts 1 + 3 harm.
    assert turn.campaign.foes[0].ticks == 8 * 4


def test_after_effects_and_follow_ups(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "berserker", 2)
    fight(turn, dice)
    dice.load(1, 9, 10)
    card = turn.make_move("attack", stat="iron", boosts=[BoostRef("berserker", 2, 1)])
    assert card is not None
    assert FollowUp("endure_stress", 1) in card.effects


def test_bonds_box_gives_experience_and_momentum(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "bonded", 2)
    turn.campaign.bonds = 3
    dice.load(6, 1, 1)
    turn.make_move("forge_a_bond", stat="heart")
    turn.resolve([[0]])
    assert turn.campaign.character.experience == 1
    assert turn.campaign.character.momentum == 2 + 2


def test_fated_two_boxes_on_the_background_vow(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "fated", 3)
    vow: ProgressTrack = turn.campaign.vows[0]
    vow.rank = Rank.DANGEROUS
    vow.ticks = 4
    dice.load(6, 1, 1)
    turn.make_move("secure_an_advantage", stat="edge")
    turn.resolve([[1]])
    turn.mark_vow(vow.name)
    assert turn.campaign.character.experience == 1


def test_reroll_only_after_a_miss(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "bonded", 3)
    dice.load(6, 1, 1)
    card = turn.make_move("face_danger", stat="edge", boosts=[BoostRef("bonded", 3)])
    assert card is not None
    assert not card.can_reroll
    with pytest.raises(TurnError, match="reroll"):
        turn.reroll([0])


def test_a_once_per_fight_use_outside_a_fight_doesnt_carry_into_one(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "cutthroat", 3)
    dice.load(6, 1, 1)
    turn.make_move("secure_an_advantage", boosts=[BoostRef("cutthroat", 3)])
    turn.resolve([[1]])
    fight(turn, dice)
    assert any(a.ref == BoostRef("cutthroat", 3) for a in turn.boosts_for("secure_an_advantage"))


def test_counted_miss_at_zero_offers_the_fate_choice(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "berserker", 3)
    turn.campaign.character.health = 1
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=2))
    # Iron 1 + 6 = 7 against 6 and 9: a weak hit on the dice, counted as a miss.
    dice.load(6, 6, 9)
    card = turn.roll_follow_up(boosts=[BoostRef("berserker", 3)])
    assert card is not None
    assert card.hit is Hit.MISS
    labels = [o.label for e in card.effects if isinstance(e, Choose) for o in e.options]
    assert "Roll on the table" in labels


def test_endure_adds_an_asset_meter(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "fortune_hunter")
    turn.campaign.character.asset("fortune_hunter").meters["wealth"] = 3
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=1))
    dice.load(1, 9, 10)
    card = turn.roll_follow_up(boosts=[BoostRef("fortune_hunter", 1, 2)])
    assert card is not None
    assert card.action is not None
    assert card.action.adds == 3
    assert turn.campaign.character.asset("fortune_hunter").meters["wealth"] == 2


def test_endure_checks_the_mask(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    give(turn, "masked")
    set_field(turn.campaign.character, datasworn(), "masked", "material", "whisperwood")
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=1))
    before = turn.campaign.model_copy(deep=True)
    with pytest.raises(TurnError, match="wits"):
        turn.roll_follow_up(boosts=[BoostRef("masked", 1)])
    assert turn.campaign == before


def test_roll_only_boosts_arent_offered_on_progress_moves(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    give(turn, "fortune_hunter")
    labels = [a.label for a in turn.boosts_for("fulfill_your_vow")]
    assert "Fortune Hunter 1: Paid" in labels
    assert "Fortune Hunter 1: Leverage wealth" not in labels


def test_veteran_initiative_needs_a_counted_weak_hit(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "veteran")
    give(turn, "improviser", 3)
    fight(turn, dice)
    turn.campaign.initiative = "foe"
    turn.campaign.character.momentum = 7
    dice.load(1, 4, 9)
    turn.make_move(
        "attack", stat="iron", boosts=[BoostRef("veteran", 1), BoostRef("improviser", 3)]
    )
    card = turn.burn()
    assert card.hit is Hit.MISS
    assert SetInitiative("character") not in card.effects


def test_old_saves_take_the_first_vow_as_the_background_vow(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    data = turn.campaign.model_dump(mode="json")
    data["background_vow"] = None
    loaded = Campaign.model_validate(data)
    assert loaded.background_vow == "Avenge my village"


def test_veteran_takes_initiative_on_a_burned_miss(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "veteran")
    fight(turn, dice)
    turn.campaign.initiative = "foe"
    turn.campaign.character.momentum = 7
    dice.load(1, 4, 9)
    turn.make_move("attack", stat="iron", boosts=[BoostRef("veteran", 1)])
    card = turn.burn()
    assert card.hit is Hit.WEAK
    assert card.effects[-1] == SetInitiative("character")
    turn.resolve()
    assert turn.campaign.initiative == "character"
