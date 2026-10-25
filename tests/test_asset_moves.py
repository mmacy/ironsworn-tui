"""Asset moves, lasting effects, and companions, through the turn engine."""

from pathlib import Path

import pytest

from ironsworn_tui.abilities import BoostRef
from ironsworn_tui.campaign import Campaign, Lasting, OwedMove
from ironsworn_tui.rules.dice import Hit
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, TurnEngine, TurnError
from tests.support import Dice, engine
from tests.test_boosts import give


def fight(turn: TurnEngine, dice: Dice) -> None:
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()


def lasting_ref(turn: TurnEngine, kind: str) -> BoostRef:
    index = next(i for i, lasting in enumerate(turn.campaign.lasting) if lasting.kind == kind)
    return BoostRef("", 0, lasting=index)


def test_asset_moves_join_the_full_list(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert "fashion_talisman" not in turn.full_list().options
    give(turn, "talisman")
    assert turn.full_list().options[-1] == "fashion_talisman"
    with pytest.raises(TurnError, match="Augur"):
        turn.make_move("augur")


def test_a_ritual_session(tmp_path: Path):
    """The plan's done criterion: perform a ritual, use its effect, and have a companion
    endure harm."""
    turn, dice, _ = engine(tmp_path)
    give(turn, "talisman")
    campaign = turn.campaign

    # Fashion Talisman: wits 3 + 4 = 7 against 2 and 5, a strong hit.
    dice.load(4, 2, 5)
    card = turn.make_move("fashion_talisman")
    assert card is not None
    assert card.rolled_with == "wits"
    turn.resolve()
    assert campaign.lasting == [Lasting(kind="talisman_2")]

    # The talisman adds +2 to Face Danger against the target, and stays.
    talisman = lasting_ref(turn, "talisman_2")
    assert [a.label for a in turn.boosts_for("face_danger")][-1] == "Talisman"
    dice.load(2, 5, 9)
    card = turn.make_move("face_danger", stat="edge", boosts=[talisman])
    assert card is not None
    assert card.action is not None
    assert card.action.adds == 2
    turn.resolve([[0]])
    assert campaign.lasting == [Lasting(kind="talisman_2")]

    # On an action die of 1, the magic is spent.
    dice.load(1, 9, 10)
    turn.make_move("face_danger", stat="edge", boosts=[talisman])
    turn.resolve()
    assert campaign.lasting == []
    turn.pay_the_price("obvious")

    # The hawk takes 2 harm: health 3 - 2 = 1, so the roll uses heart 2.
    # Heart 2 + 5 = 7 against 3 and 6: a strong hit, and the hawk rallies.
    campaign.follow_ups.append(OwedMove(move="companion_endure_harm", amount=2, asset="hawk"))
    dice.load(5, 3, 6)
    card = turn.roll_follow_up()
    assert card is not None
    assert card.rolled_with == "heart"
    assert card.hit is Hit.STRONG
    turn.resolve()
    assert campaign.character.asset("hawk").meters["health"] == 2

    turn.save()
    assert Campaign.load(tmp_path / "kira.json") == campaign


def test_one_time_lasting_effect_ends_when_used(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "fletcher", 3)
    dice.load(6, 1, 1)
    turn.make_move("craft_arrow")
    turn.resolve()
    assert [lasting.kind for lasting in turn.campaign.lasting] == ["seeker_arrow", "ravager_arrow"]
    fight(turn, dice)
    # Iron 1 + 1 = 2 against 9 and 10: a miss, then the Seeker arrow's reroll.
    dice.load(1, 9, 10)
    card = turn.make_move("attack", stat="iron", boosts=[lasting_ref(turn, "seeker_arrow")])
    assert card is not None
    assert card.can_reroll
    assert [lasting.kind for lasting in turn.campaign.lasting] == ["ravager_arrow"]


def test_ravager_inflicts_a_rolled_extra_harm(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.lasting.append(Lasting(kind="ravager_arrow"))
    turn.campaign.character.harm = 1
    fight(turn, dice)
    dice.load(6, 1, 1)
    turn.make_move("attack", stat="iron", boosts=[lasting_ref(turn, "ravager_arrow")])
    dice.load(2)
    turn.resolve()
    # A strong hit inflicts harm 1 + 1, then the Ravager's 2.
    assert turn.campaign.foes[0].ticks == 8 * 4


def test_elixir_needs_its_stat_and_ends_at_low_health(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.lasting.append(Lasting(kind="elixir", stat="wits"))
    elixir = lasting_ref(turn, "elixir")
    with pytest.raises(TurnError, match="wits"):
        turn.make_move("face_danger", stat="edge", boosts=[elixir])
    turn.campaign.character.health = 0
    dice.load(6, 1, 1)
    turn.make_move("face_danger", stat="wits", boosts=[elixir])
    turn.resolve()
    assert turn.campaign.lasting == []


def test_create_elixir_costs_supply_and_offers_two_with_the_upgrade(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "alchemist", 2)
    dice.load(6, 1, 1)
    card = turn.make_move("create_elixir")
    assert card is not None
    assert turn.campaign.character.supply == 4
    turn.resolve([[4, 1]])
    assert turn.campaign.lasting == [
        Lasting(kind="elixir", stat="wits"),
        Lasting(kind="elixir", stat="heart"),
    ]


def test_invoke_adds_the_action_die_to_essence(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "invoke")
    dice.load(5, 1, 1)
    turn.make_move("invoke")
    turn.resolve()
    assert turn.campaign.character.asset("invoke").meters["essence"] == 5


def test_capture_light_sets_the_light(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "lightbearer")
    dice.load(1, 2, 9)
    turn.make_move("capture_light")
    turn.resolve()
    assert turn.campaign.character.asset("lightbearer").meters["light"] == 3


def test_ritual_boost_on_its_move(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "augur", 3)
    dice.load(1, 5, 9)
    card = turn.make_move("augur", boosts=[BoostRef("augur", 3)])
    assert card is not None
    assert card.action is not None
    assert card.action.adds == 1


def test_companion_dies_on_a_miss_with_a_one_at_zero(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.follow_ups.append(OwedMove(move="companion_endure_harm", amount=5, asset="hawk"))
    dice.load(1, 9, 10)
    card = turn.roll_follow_up()
    assert card is not None
    assert card.hit is Hit.MISS
    # The hawk had 3 health, so 2 harm spills over as -2 momentum.
    assert turn.campaign.character.momentum == 0
    turn.resolve()
    assert turn.campaign.character.asset_or_none("hawk") is None
    # Hawk has one marked ability.
    assert turn.campaign.character.experience == 1


def test_companion_harm_needs_a_companion(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.campaign.follow_ups.append(OwedMove(move="companion_endure_harm", amount=1))
    turn.campaign.character.assets.pop(1)
    with pytest.raises(TurnError, match="companion"):
        turn.roll_follow_up()


def test_make_camp_heals_companions(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.character.asset("hawk").meters["health"] = 1
    dice.load(6, 1, 1)
    turn.make_move("make_camp")
    turn.resolve([[0, 3]])
    assert turn.campaign.character.asset("hawk").meters["health"] == 2


def test_heal_a_companion(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.character.asset("hawk").meters["health"] = 0
    dice.load(6, 1, 1)
    turn.make_move("heal", stat="wits", inputs=MoveInputs(heal_self=False, companion="hawk"))
    turn.resolve()
    assert turn.campaign.character.asset("hawk").meters["health"] == 2
    assert turn.campaign.character.health == 5


def test_a_mortal_wound_owes_face_death(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    character = turn.campaign.character
    character.health = 0
    character.mark_debility("wounded")
    character.mark_debility("maimed")
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=1))
    dice.load(1, 9, 10)
    card = turn.roll_follow_up()
    assert card is not None
    dice.load(5)
    turn.resolve([[0]])
    assert turn.follow_ups == (OwedMove(move="face_death"),)
    dice.load(6, 1, 1)
    card = turn.roll_follow_up()
    assert card is not None
    assert card.rolled_with == "heart"
    assert card.hit is Hit.STRONG


def test_fated_answers_face_death(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    give(turn, "fated")
    turn.campaign.follow_ups.append(OwedMove(move="face_death"))
    card = turn.roll_follow_up(boosts=[BoostRef("fated", 1)])
    assert card is not None
    assert card.hit is Hit.STRONG
    turn.resolve()
    assert turn.campaign.character.asset("fated").debility


def test_outcast_scrapes_by(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    give(turn, "outcast")
    turn.campaign.character.supply = 1
    dice.load(1, 9, 10)
    turn.make_move("face_danger", stat="edge")
    turn.resolve()
    turn.pay_the_price("obvious")
    dice.load(3, 4, 6)
    turn.make_move("face_danger", stat="edge")
    turn.resolve([[3]])
    assert "unprepared" not in turn.campaign.character.debilities
    assert turn.follow_ups == (OwedMove(move="scrape_by"),)
    dice.load(6, 1, 1)
    card = turn.roll_follow_up()
    assert card is not None
    assert card.rolled_with == "wits"
    turn.resolve()
    assert turn.campaign.character.supply == 1


def test_end_a_lasting_effect_by_hand(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.campaign.lasting.append(Lasting(kind="commune"))
    turn.end_lasting(0)
    assert turn.campaign.lasting == []
    with pytest.raises(TurnError, match="no lasting"):
        turn.end_lasting(0)
