"""The turn loop, driven through a scripted session with fixed dice and fixture decisions."""

from pathlib import Path

import pytest

from ironsworn_tui.abilities import BoostRef
from ironsworn_tui.campaign import Campaign, Lasting, OwedMove
from ironsworn_tui.moves import Context
from ironsworn_tui.outcomes import Choose, Note
from ironsworn_tui.rules.dice import Hit
from ironsworn_tui.rules.oracles import OracleResult, YesNo
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, RollCard, TurnEngine, TurnError
from tests.support import Dice, engine


def test_scripted_session(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    campaign = turn.campaign
    kira = campaign.character

    # Swear a vow: heart 2 + 5 = 7 against 3 and 4 is a strong hit, +2 momentum.
    dice.load(5, 3, 4)
    card = turn.make_move(
        "swear_an_iron_vow", inputs=MoveInputs(vow="Find my brother", rank=Rank.DANGEROUS)
    )
    assert card is not None
    assert card.hit is Hit.STRONG
    assert turn.resolve() == ()
    assert kira.momentum == 4
    assert [vow.name for vow in campaign.vows] == ["Avenge my village", "Find my brother"]

    # Face Danger, suggested by the model: edge 2 + 3 = 5 against 4 and 6 is a weak hit.
    decider.answers.append(("face_danger", "edge", 0.95))
    suggestion = turn.suggest("I edge along the ledge, keeping my weight on the balls of my feet.")
    assert suggestion.band == "act"
    assert suggestion.options == ("face_danger",)
    assert suggestion.decision is not None
    stat = suggestion.decision.stat_for("face_danger")
    assert stat is not None
    assert stat.choice == "edge"
    dice.load(3, 4, 6)
    card = turn.make_move("face_danger", stat="edge")
    assert card is not None
    assert card.hit is Hit.WEAK
    turn.resolve([[3]])  # You sacrifice resources: -1 supply.
    assert (kira.supply, kira.momentum) == (4, 4)

    # Enter the Fray against two foes: shadow 1 + 6 = 7 against 2 and 5 is a strong hit.
    dice.load(6, 2, 5)
    foes = (("Raider chief", Rank.DANGEROUS), ("Raider archer", Rank.TROUBLESOME))
    card = turn.make_move("enter_the_fray", stat="shadow", inputs=MoveInputs(foes=foes))
    assert card is not None
    turn.resolve()
    assert campaign.context is Context.FIGHT
    assert [foe.name for foe in campaign.foes] == ["Raider chief", "Raider archer"]
    assert (kira.momentum, campaign.initiative, campaign.target) == (6, "character", "Raider chief")

    # Strike, with initiative and a deadly weapon: iron 1 + 6 = 7 against 1 and 3 is a strong
    # hit, 2 + 1 harm against a dangerous foe, 24 ticks.
    dice.load(6, 1, 3)
    card = turn.make_move("attack", stat="iron")
    assert card is not None
    assert card.move == "strike"
    turn.resolve()
    assert campaign.foes[0].ticks == 24
    assert (kira.momentum, campaign.initiative, campaign.end_fight_offered) == (
        6,
        "character",
        True,
    )

    # Another Strike misses: iron 1 + 1 = 2 against 8 and 9. Pay the Price on the table.
    dice.load(1, 8, 9)
    card = turn.make_move("attack", stat="iron")
    assert card is not None
    assert card.hit is Hit.MISS
    assert card.burn_available is False
    assert turn.resolve() == (OwedMove(move="pay_the_price"),)
    assert (kira.momentum, campaign.initiative, campaign.end_fight_offered) == (6, "foe", False)
    dice.load(45)
    result = turn.pay_the_price("table")
    assert isinstance(result, OracleResult)
    assert result.text == "A new danger or foe is revealed."
    assert turn.follow_ups == ()

    # Turn the Tide: the attack becomes a Strike with +1. Edge 2 + 1 + 4 = 7 against 5 and 6.
    turn.arm_tide()
    dice.load(4, 5, 6)
    card = turn.make_move("attack", stat="edge")
    assert card is not None
    assert (card.move, card.tide, card.hit) == ("strike", True, Hit.STRONG)
    assert card.action is not None
    assert card.action.adds == 1
    turn.resolve()
    assert campaign.foes[0].ticks == 40
    assert (kira.momentum, campaign.initiative, campaign.tide_used) == (7, "character", True)
    assert campaign.end_fight_offered is True
    with pytest.raises(TurnError):
        turn.arm_tide()

    # End the Fight: 10 boxes against 3 and 7 is a strong hit. The chief is out.
    dice.load(3, 7)
    card = turn.make_move("end_the_fight")
    assert card is not None
    assert card.progress is not None
    assert card.progress.score == 10
    turn.resolve()
    assert [foe.name for foe in campaign.foes] == ["Raider archer"]
    assert (campaign.target, campaign.initiative) == ("Raider archer", "character")

    # The campaign was saved after the turn, and reloads the same.
    reloaded = Campaign.load(tmp_path / "kira.json")
    assert reloaded == campaign
    assert reloaded.character.momentum == 7
    assert reloaded.foes[0].ticks == 0
    assert reloaded.tide_used is True


def test_weak_hit_can_lead_to_endure_harm(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    kira = turn.campaign.character
    dice.load(3, 4, 6)
    turn.make_move("face_danger", stat="edge")
    assert turn.resolve([[1]]) == (OwedMove(move="endure_harm", amount=1),)
    # Health 5 - 1 = 4, then roll +health: 4 + 2 = 6 against 7 and 8 is a miss, -1 momentum.
    dice.load(2, 7, 8)
    card = turn.roll_follow_up()
    assert card is not None
    assert card.hit is Hit.MISS
    assert card.rolled_with == "health"
    assert kira.health == 4
    turn.resolve()
    assert kira.momentum == 1


def test_miss_at_zero_health_offers_the_fate_choice(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    kira = turn.campaign.character
    kira.health = 1
    kira.momentum = 0
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=2))
    dice.load(1, 9, 10)
    card = turn.roll_follow_up()
    assert card is not None
    assert kira.health == 0
    assert kira.momentum == -1
    choices = [effect for effect in card.effects if isinstance(effect, Choose)]
    labels = [option.label for option in choices[-1].options]
    assert labels == ["Mark wounded", "Mark maimed", "Roll on the table"]
    turn.resolve([[0]])
    assert kira.debilities == ["wounded"]
    assert kira.momentum == -2


def test_burning_momentum_resets_it(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    kira = turn.campaign.character
    kira.momentum = 8
    dice.load(1, 5, 7)
    card = turn.make_move("face_danger", stat="iron")
    assert card is not None
    assert card.hit is Hit.MISS
    assert card.burn_available
    burned = turn.burn()
    assert burned.hit is Hit.STRONG
    assert kira.momentum == 2
    turn.resolve()
    assert kira.momentum == 3


def test_failed_request_offers_the_full_list(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.decider = None
    suggestion = turn.suggest("I look around.")
    assert suggestion.band == "escalate"
    assert "face_danger" in suggestion.options
    assert "no_move" not in suggestion.options


def test_no_move_answer_logs_the_message_without_a_roll(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    decider.answers.append(("no_move", None, 0.9))
    suggestion = turn.suggest("I share a meal with Ulla.")
    assert suggestion.band == "no_roll"
    assert turn.campaign.log[-1].text == "I share a meal with Ulla."


def test_middling_confidence_offers_the_top_two(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    decider.answers.append(("secure_an_advantage", "wits", 0.6))
    suggestion = turn.suggest("I study the camp before we move in.")
    assert suggestion.band == "confirm"
    assert len(suggestion.options) == 2
    assert suggestion.options[0] == "secure_an_advantage"


def test_state_sent_to_the_model_names_the_foes(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    turn.set_scene("A raider camp at the ford.")
    dice.load(6, 2, 5)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    decider.answers.append(("attack", "iron", 0.9))
    turn.suggest("I swing at him.")
    state = decider.requests[-1]["state"]
    assert state["situation"] == "A raider camp at the ford. Foes: Raider."
    assert state["circumstances"] == "Kira is in a fight and has initiative."


def test_moves_outside_the_context_are_refused(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(TurnError, match="context"):
        turn.make_move("attack", stat="iron")
    with pytest.raises(TurnError, match="stats"):
        turn.make_move("face_danger")
    with pytest.raises(TurnError):
        turn.arm_tide()


def test_forsaking_a_vow_endures_stress_by_rank(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert turn.make_move("forsake_your_vow") is None
    assert turn.campaign.vows == []
    assert turn.follow_ups == (OwedMove(move="endure_stress", amount=5),)


def test_fulfilling_a_vow_marks_experience(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    vow = turn.campaign.vows[0]
    vow.ticks = 40
    dice.load(3, 4)
    card = turn.make_move("fulfill_your_vow")
    assert card is not None
    assert card.hit is Hit.STRONG
    turn.resolve()
    assert turn.campaign.vows == []
    assert turn.campaign.character.experience == 5


def test_journey_progress_and_arrival(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 2)
    turn.make_move(
        "undertake_a_journey", inputs=MoveInputs(destination="Highcairn", rank=Rank.DANGEROUS)
    )
    turn.resolve([[0]])
    journey = turn.campaign.journey
    assert journey is not None
    assert journey.ticks == 8
    assert turn.campaign.context is Context.JOURNEY
    journey.ticks = 36
    dice.load(2, 4)
    turn.make_move("reach_your_destination")
    turn.resolve([[1]])
    assert turn.campaign.journey is None
    assert turn.campaign.character.momentum == 3


def test_supply_at_zero_marks_unprepared(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    kira = turn.campaign.character
    kira.supply = 1
    dice.load(3, 4, 6)
    turn.make_move("face_danger", stat="edge")
    turn.resolve([[3]])
    assert kira.supply == 0
    assert "unprepared" in kira.debilities


def fight(turn: TurnEngine, dice: Dice, *foes: tuple[str, Rank]) -> None:
    """Start a fight with a strong hit on Enter the Fray."""
    dice.load(6, 1, 1)
    turn.make_move("enter_the_fray", stat="heart", inputs=MoveInputs(foes=foes))
    turn.resolve()


def test_forsake_as_a_follow_up_leads_to_endure_stress(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(1, 9, 10)
    turn.make_move(
        "swear_an_iron_vow", inputs=MoveInputs(vow="Find my brother", rank=Rank.DANGEROUS)
    )
    assert turn.resolve([[1]]) == (OwedMove(move="forsake_your_vow", vow="Find my brother"),)
    assert turn.forsake() == (OwedMove(move="endure_stress", amount=2),)
    assert [vow.name for vow in turn.campaign.vows] == ["Avenge my village"]
    dice.load(6, 1, 1)
    turn.roll_follow_up()
    turn.resolve([[0]])
    assert turn.follow_ups == ()


def test_end_the_fight_needs_an_offer(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    fight(turn, dice, ("Raider", Rank.DANGEROUS))
    with pytest.raises(TurnError, match="strong hit"):
        turn.make_move("end_the_fight")


def test_end_the_fight_weak_hit_harm_comes_from_the_beaten_foe(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    fight(turn, dice, ("Wyrm", Rank.EXTREME))
    turn.campaign.foes[0].ticks = 20
    dice.load(6, 1, 1)
    turn.make_move("attack", stat="iron")
    turn.resolve()
    assert turn.campaign.end_fight_offered
    dice.load(4, 9)
    card = turn.make_move("end_the_fight")
    assert card is not None
    assert card.hit is Hit.WEAK
    assert turn.resolve([[0]]) == (OwedMove(move="endure_harm", amount=4),)
    assert turn.campaign.foes == []


def test_initiative_follows_the_hit_on_other_moves(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    fight(turn, dice, ("Raider", Rank.DANGEROUS))
    campaign = turn.campaign
    dice.load(3, 4, 6)
    turn.make_move("face_danger", stat="edge")
    turn.resolve([[0]])
    assert campaign.initiative == "foe"
    dice.load(6, 1, 1)
    turn.make_move("face_danger", stat="edge")
    turn.resolve()
    assert campaign.initiative == "character"


def test_strong_hit_on_endure_harm_takes_initiative(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    fight(turn, dice, ("Raider", Rank.DANGEROUS))
    dice.load(1, 9, 10)
    turn.make_move("attack", stat="iron")
    turn.resolve()
    turn.pay_the_price("obvious")
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=2))
    dice.load(6, 1, 1)
    turn.roll_follow_up()
    turn.resolve([[1]])
    assert turn.campaign.initiative == "character"


def test_clash_with_an_opening_offers_end_the_fight(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.character.harm = 1
    fight(turn, dice, ("Dragon", Rank.EPIC))
    campaign = turn.campaign
    campaign.initiative = "foe"
    campaign.foes[0].ticks = 2
    dice.load(6, 1, 1)
    card = turn.make_move("attack", stat="iron")
    assert card is not None
    assert card.move == "clash"
    turn.resolve([[1]])
    assert campaign.foes[0].ticks == 4
    assert campaign.end_fight_offered


def test_required_choices_cannot_be_skipped(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(3, 4, 6)
    turn.make_move("face_danger", stat="edge")
    with pytest.raises(TurnError, match="choose 1 to 1"):
        turn.resolve([[]])
    turn.resolve([[3]])
    assert turn.campaign.character.supply == 4


def test_boasts_are_optional(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    turn.make_move("draw_the_circle", inputs=MoveInputs(foes=(("Rival", Rank.DANGEROUS),)))
    turn.resolve([[]])
    assert turn.campaign.character.momentum == 3


def test_a_refused_move_changes_nothing(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    before = turn.campaign.model_copy(deep=True)
    with pytest.raises(TurnError, match="stats"):
        turn.make_move("enter_the_fray", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),)))
    assert turn.campaign == before
    assert turn.campaign.context is Context.EXPLORING


def test_a_refused_tide_move_keeps_initiative(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    fight(turn, dice, ("Raider", Rank.DANGEROUS))
    turn.campaign.initiative = "foe"
    turn.arm_tide()
    with pytest.raises(TurnError):
        turn.make_move("attack")
    assert turn.campaign.initiative == "foe"
    turn.disarm_tide()
    assert turn.campaign.tide_armed is False


def test_a_failed_tide_pays_the_price_once(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    fight(turn, dice, ("Raider", Rank.DANGEROUS))
    turn.campaign.initiative = "foe"
    turn.arm_tide()
    dice.load(1, 9, 10)
    turn.make_move("attack", stat="iron")
    assert turn.resolve() == (OwedMove(move="pay_the_price"),)


def test_blocked_options_are_not_offered(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    kira = turn.campaign.character
    kira.health = 2
    kira.mark_debility("wounded")
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=1))
    dice.load(6, 1, 1)
    card = turn.roll_follow_up()
    assert card is not None
    labels = [o.label for e in card.effects if isinstance(e, Choose) for o in e.options]
    assert labels == ["Embrace the pain: +1 momentum"]


def test_resupply_is_refused_while_unprepared(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.campaign.character.supply = 0
    turn.campaign.character.mark_debility("unprepared")
    with pytest.raises(TurnError, match="unprepared"):
        turn.make_move("resupply")


def test_no_new_move_while_a_follow_up_is_owed(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(1, 9, 10)
    turn.make_move("face_danger", stat="edge")
    turn.resolve()
    with pytest.raises(TurnError, match="Pay the Price"):
        turn.make_move("face_danger", stat="edge")


def test_owed_follow_ups_survive_a_restart(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(1, 9, 10)
    turn.make_move("face_danger", stat="edge")
    turn.resolve()
    reloaded = Campaign.load(tmp_path / "kira.json")
    assert reloaded.follow_ups == [OwedMove(move="pay_the_price")]


def test_pay_the_price_by_asking_the_oracle(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.follow_ups.append(OwedMove(move="pay_the_price"))
    dice.load(30)
    result = turn.pay_the_price("ask")
    assert isinstance(result, YesNo)
    assert result.yes is True


def test_duplicate_foe_names_are_refused(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    foes = (("Raider", Rank.DANGEROUS), ("Raider", Rank.DANGEROUS))
    with pytest.raises(TurnError, match="different name"):
        turn.make_move("enter_the_fray", stat="heart", inputs=MoveInputs(foes=foes))


def test_supply_loss_at_zero_notes_the_exchange(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    kira = turn.campaign.character
    kira.supply = 0
    kira.mark_debility("unprepared")
    dice.load(3, 4, 6)
    turn.make_move("face_danger", stat="edge")
    turn.resolve([[3]])
    assert "exchange 1 supply" in turn.campaign.log[-1].text


def test_heal_on_someone_else_leaves_your_health(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.character.health = 3
    dice.load(6, 1, 1)
    card = turn.make_move("heal", inputs=MoveInputs(heal_self=False))
    assert card is not None
    assert card.rolled_with == "wits"
    turn.resolve()
    assert turn.campaign.character.health == 3


def test_burning_momentum_on_endure_harm_rebuilds_the_card(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    kira = turn.campaign.character
    kira.health = 1
    kira.momentum = 9
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=1))
    dice.load(1, 4, 8)
    card = turn.roll_follow_up()
    assert card is not None
    assert any(
        isinstance(e, Choose) and e.options[-1].label == "Roll on the table" for e in card.effects
    )
    burned = turn.burn()
    assert burned.hit is Hit.STRONG
    assert not any(
        isinstance(e, Choose) and e.options[-1].label == "Roll on the table" for e in burned.effects
    )


def test_declining_the_end_the_fight_offer(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    dice.load(6, 1, 1)
    turn.make_move("attack", stat="iron")
    turn.resolve()
    assert turn.campaign.end_fight_offered is True
    turn.decline_end_fight()
    assert turn.campaign.end_fight_offered is False
    with pytest.raises(TurnError):
        turn.make_move("end_the_fight")


def test_endure_owes_the_move(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.endure("endure_harm", 2)
    assert turn.follow_ups == (OwedMove(move="endure_harm", amount=2),)
    dice.load(6, 1, 1)
    card = turn.roll_follow_up()
    assert card is not None and card.move == "endure_harm"
    turn.resolve([[1]])
    assert turn.campaign.character.health == 3
    with pytest.raises(TurnError):
        turn.endure("endure_harm", 0)


def test_aid_your_ally_is_on_the_full_list_in_every_context(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    assert "aid_your_ally" in turn.full_list().options
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    assert "aid_your_ally" in turn.full_list().options


def test_aid_your_ally_gives_the_benefits_to_the_ally(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    momentum = turn.campaign.character.momentum
    dice.load(6, 1, 1)
    card = turn.make_move("aid_your_ally", stat="edge")
    assert card is not None
    assert (card.name, card.rolled_with, card.hit) == ("Aid Your Ally", "edge", Hit.STRONG)
    assert "they (instead of you)" in card.outcome_text
    assert all(isinstance(effect, Note) for effect in card.effects)
    turn.resolve()
    assert turn.campaign.character.momentum == momentum


def test_aid_your_ally_in_a_fight_takes_initiative_on_a_strong_hit(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(1, 9, 9)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    assert turn.campaign.initiative == "foe"
    turn.pay_the_price("obvious")
    dice.load(6, 1, 1)
    turn.make_move("aid_your_ally", stat="edge")
    turn.resolve()
    assert turn.campaign.initiative == "character"


def test_aid_your_ally_miss_pays_the_price(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(1, 9, 9)
    turn.make_move("aid_your_ally", stat="edge")
    turn.resolve()
    assert turn.follow_ups == (OwedMove(move="pay_the_price"),)


def first_choice(card: RollCard) -> Choose:
    return next(effect for effect in card.effects if isinstance(effect, Choose))


def test_sojourn_asks_whether_you_share_a_bond(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert turn.inputs_needed("sojourn") == ("bond",)


def test_sojourn_with_a_bond_adds_1_and_one_more_choice(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    kira = turn.campaign.character
    kira.spirit, kira.supply = 2, 2
    # Heart 2 + 3 + 1 for the bond = 6 against 5 and 6 is a weak hit: choose one, and one more.
    dice.load(3, 5, 6)
    card = turn.make_move("sojourn", inputs=MoveInputs(bond=True))
    assert card is not None
    assert card.action is not None
    assert (card.hit, card.action.adds) == (Hit.WEAK, 1)
    choice = first_choice(card)
    assert (choice.minimum, choice.count) == (2, 2)
    turn.resolve([[4, 5]])
    assert (kira.spirit, kira.supply) == (4, 4)


def test_sojourn_without_a_bond_chooses_two_on_a_strong_hit(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    card = turn.make_move("sojourn")
    assert card is not None
    assert card.action is not None
    assert card.action.adds == 0
    choice = first_choice(card)
    assert (choice.minimum, choice.count) == (2, 2)
    dice.load(6, 1, 1)
    turn.resolve([[3, 6]])
    card = turn.make_move("sojourn", inputs=MoveInputs(bond=True))
    assert card is not None
    assert first_choice(card).count == 3


def draw_the_circle(turn: TurnEngine, dice: Dice, boasts: list[int]) -> None:
    """Draw the Circle against a dangerous rival with a strong hit, and make the boasts."""
    dice.load(6, 1, 1)
    turn.make_move("draw_the_circle", inputs=MoveInputs(foes=(("Rival", Rank.DANGEROUS),)))
    turn.resolve([boasts])


def test_draw_the_circle_allows_up_to_three_boasts(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    draw_the_circle(turn, dice, [0, 1, 2])
    assert turn.campaign.character.momentum == 6
    assert turn.campaign.initiative == "foe"


def test_bare_yourself_adds_1_to_the_foes_harm_until_the_fight_ends(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    campaign = turn.campaign
    draw_the_circle(turn, dice, [1])
    assert campaign.foe_harm_bonus == 1
    turn.endure("endure_harm", None)
    assert turn.follow_ups == (OwedMove(move="endure_harm", amount=3),)
    dice.load(6, 1, 1)
    turn.roll_follow_up()
    turn.resolve([[1]])
    assert campaign.character.health == 2
    turn.end_fight("the rival yields")
    assert campaign.foe_harm_bonus == 0


def test_bare_yourself_raises_the_harm_end_the_fight_can_cost(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    draw_the_circle(turn, dice, [1])
    # A strong hit on Strike marks 24 ticks, so End the Fight rolls 6 against 4 and 9.
    dice.load(6, 1, 1)
    turn.make_move("attack", stat="iron")
    turn.resolve()
    dice.load(4, 9)
    turn.make_move("end_the_fight")
    assert turn.resolve([[0]]) == (OwedMove(move="endure_harm", amount=3),)


def test_endure_harm_without_an_amount_needs_a_fight(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(TurnError, match="fight"):
        turn.endure("endure_harm", None)


def test_hold_no_iron_sets_your_harm_to_1_until_the_fight_ends(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    campaign = turn.campaign
    kira = campaign.character
    draw_the_circle(turn, dice, [2])
    assert kira.harm == 1
    # A strong hit on Strike inflicts 1 + 1 harm: 2 boxes each against a dangerous foe.
    dice.load(6, 1, 1)
    turn.make_move("attack", stat="iron")
    turn.resolve()
    assert campaign.foes[0].ticks == 16
    turn.end_fight("the rival yields")
    assert kira.harm == 2
    assert Campaign.load(tmp_path / "kira.json").character.harm == 2


def test_hold_no_iron_ends_when_end_the_fight_beats_the_last_foe(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    draw_the_circle(turn, dice, [2])
    turn.campaign.foes[0].ticks = 40
    turn.campaign.initiative = "character"
    dice.load(6, 1, 1)
    turn.make_move("attack", stat="iron")
    turn.resolve()
    dice.load(1, 1)
    turn.make_move("end_the_fight")
    turn.resolve()
    assert turn.campaign.foes == []
    assert turn.campaign.character.harm == 2


def test_any_strong_hit_in_a_fight_offers_end_the_fight(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    fight(turn, dice, ("Raider", Rank.DANGEROUS))
    campaign = turn.campaign
    campaign.foes[0].ticks = 8
    dice.load(6, 1, 1)
    turn.make_move("face_danger", stat="edge")
    turn.resolve()
    assert campaign.end_fight_offered
    turn.decline_end_fight()
    dice.load(6, 1, 1)
    turn.make_move("secure_an_advantage", stat="wits")
    turn.resolve([[0]])
    assert campaign.end_fight_offered


def test_a_strong_hit_on_a_suffer_move_offers_no_end_the_fight(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    fight(turn, dice, ("Raider", Rank.DANGEROUS))
    turn.campaign.foes[0].ticks = 8
    turn.endure("endure_harm", 1)
    dice.load(6, 1, 1)
    turn.roll_follow_up()
    turn.resolve([[1]])
    assert not turn.campaign.end_fight_offered


def reloaded(turn: TurnEngine, tmp_path: Path, dice: Dice) -> TurnEngine:
    """A new engine on the saved campaign, as after quitting and reopening the app."""
    path = tmp_path / "kira.json"
    return TurnEngine(Campaign.load(path), turn.data, dice, turn.thresholds, path=path)


def test_an_unresolved_card_survives_a_restart(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(3, 4, 6)
    card = turn.make_move("face_danger", stat="edge")
    again = reloaded(turn, tmp_path, dice)
    assert again.card == card
    again.resolve([[3]])
    assert again.campaign.character.supply == 4
    assert reloaded(again, tmp_path, dice).card is None


def test_a_reloaded_card_can_still_burn_momentum(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.character.momentum = 8
    dice.load(1, 6, 7)
    card = turn.make_move("face_danger", stat="edge")
    assert card is not None
    assert card.burn_available
    again = reloaded(turn, tmp_path, dice)
    burned = again.burn()
    assert burned.hit is Hit.STRONG
    assert reloaded(again, tmp_path, dice).card == burned


def test_a_reloaded_vow_card_marks_the_saved_vow(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    card = turn.make_move("swear_an_iron_vow", inputs=MoveInputs(vow="Find Ash", rank=Rank.EPIC))
    again = reloaded(turn, tmp_path, dice)
    assert again.card == card
    again.resolve()
    assert [vow.name for vow in again.campaign.vows] == ["Avenge my village", "Find Ash"]
    assert again.campaign.character.momentum == 4


def test_a_reloaded_endure_harm_card_keeps_the_harm_taken(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.endure("endure_harm", 5)
    dice.load(1, 9, 9)
    card = turn.roll_follow_up()
    assert card is not None
    again = reloaded(turn, tmp_path, dice)
    assert again.card == card
    assert again.campaign.character.health == 0
    again.resolve([[0]])
    assert again.campaign.character.debilities == ["wounded"]


def test_a_reloaded_end_the_fight_card(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    fight(turn, dice, ("Raider", Rank.DANGEROUS))
    turn.campaign.foes[0].ticks = 40
    dice.load(6, 1, 1)
    turn.make_move("attack", stat="iron")
    turn.resolve()
    dice.load(1, 1)
    card = turn.make_move("end_the_fight")
    again = reloaded(turn, tmp_path, dice)
    assert again.card == card
    again.resolve()
    assert again.campaign.foes == []


def test_a_reloaded_card_keeps_a_used_up_lasting_boost(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.lasting.append(Lasting(kind="trophy_sojourn"))
    dice.load(1, 9, 9)
    card = turn.make_move("sojourn", boosts=[BoostRef("", 0, lasting=0)])
    assert card is not None
    assert card.can_reroll
    assert turn.campaign.lasting == []
    again = reloaded(turn, tmp_path, dice)
    assert again.card == card
    dice.load(1, 1)
    assert again.reroll([1, 2]).hit is Hit.STRONG
