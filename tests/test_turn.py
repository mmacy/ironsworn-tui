"""The turn loop, driven through a scripted session with fixed dice and fixture decisions."""

from pathlib import Path

import pytest

from ironsworn_tui.campaign import Campaign, OwedMove
from ironsworn_tui.moves import Context
from ironsworn_tui.outcomes import Choose
from ironsworn_tui.rules.dice import Hit
from ironsworn_tui.rules.oracles import OracleResult, YesNo
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, TurnEngine, TurnError
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
    card = turn.endure()
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
    card = turn.endure()
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
    turn.endure()
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
    turn.endure()
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
    card = turn.endure()
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
    card = turn.endure()
    assert any(
        isinstance(e, Choose) and e.options[-1].label == "Roll on the table" for e in card.effects
    )
    burned = turn.burn()
    assert burned.hit is Hit.STRONG
    assert not any(
        isinstance(e, Choose) and e.options[-1].label == "Roll on the table" for e in burned.effects
    )
