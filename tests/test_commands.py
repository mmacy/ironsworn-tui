"""The `/` commands."""

from collections.abc import Callable
from pathlib import Path

import pytest

from ironsworn_tui.campaign import Campaign, Lasting, OwedMove
from ironsworn_tui.commands import CommandError, find_table, parse_foes, run_command
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.dice import Hit
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, TurnError
from tests.support import engine


def test_scene_replaces_the_situation(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/scene A raider camp at the ford.")
    assert turn.campaign.situation == "A raider camp at the ford."
    assert turn.campaign.log[-1].text == "Scene: A raider camp at the ford."
    assert Campaign.load(tmp_path / "kira.json").situation == "A raider camp at the ford."


def test_oracle_by_short_name(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(2)
    run_command(turn, "/oracle action")
    assert turn.campaign.log[-1].text == "Oracle classic/action_and_theme/action, 2: Clash"


def test_ambiguous_or_unknown_oracle_names_are_refused():
    with pytest.raises(CommandError, match="no oracle"):
        find_table(datasworn(), "weather")


@pytest.mark.parametrize(("roll", "answer"), [(26, "yes"), (25, "no")])
def test_ask_the_oracle(tmp_path: Path, roll: int, answer: str):
    turn, dice, _ = engine(tmp_path)
    dice.load(roll)
    run_command(turn, "/ask likely")
    assert turn.campaign.log[-1].text == f"Ask the Oracle (likely), {roll}: {answer}"


def test_ask_needs_a_likelihood(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError, match="likelihood"):
        run_command(turn, "/ask maybe")


def test_vow_swear_makes_the_move(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(5, 3, 4)
    result = run_command(turn, "/vow swear dangerous Find my brother")
    assert result.card is not None
    assert result.card.hit is Hit.STRONG
    turn.resolve()
    assert [vow.name for vow in turn.campaign.vows] == ["Avenge my village", "Find my brother"]


def test_vow_mark_reaches_a_milestone(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/vow mark")
    assert turn.campaign.vows[0].ticks == 1


def test_vow_lists_the_vows(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert run_command(turn, "/vow").lines == ("Avenge my village (epic): 0/10",)


ADJUSTMENTS: list[tuple[str, Callable[[Campaign], bool]]] = [
    ("/adjust health -2", lambda c: c.character.health == 3),
    ("/adjust momentum +3", lambda c: c.character.momentum == 5),
    ("/adjust wounded mark", lambda c: c.character.debilities == ["wounded"]),
    ("/adjust bonds 2", lambda c: c.bonds == 2),
    ('/adjust vow "Avenge my village" 4', lambda c: c.vows[0].ticks == 4),
    ("/adjust vow Avenge my village 4", lambda c: c.vows[0].ticks == 4),
    ("/adjust harm 1", lambda c: c.character.harm == 1),
]


@pytest.mark.parametrize(("command", "check"), ADJUSTMENTS)
def test_adjust(tmp_path: Path, command: str, check: Callable[[Campaign], bool]):
    turn, _, _ = engine(tmp_path)
    run_command(turn, command)
    assert check(turn.campaign)


def test_adjust_fight_end(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    run_command(turn, "/adjust fight end")
    assert turn.campaign.foes == []


def test_bad_adjust_shows_the_usage(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError, match="usage"):
        run_command(turn, "/adjust luck 3")


def test_tide_outside_a_fight_is_refused(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(TurnError):
        run_command(turn, "/tide")


def test_moves_shows_the_full_list(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert run_command(turn, "/moves").show_moves


def test_unknown_command_lists_the_commands(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError, match="/oracle"):
        run_command(turn, "/dance")


def test_parse_foes():
    assert parse_foes("Raider chief dangerous, Archer troublesome") == (
        ("Raider chief", Rank.DANGEROUS),
        ("Archer", Rank.TROUBLESOME),
    )
    with pytest.raises(CommandError):
        parse_foes("Raider")


def test_target_needs_a_name(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError, match="usage"):
        run_command(turn, "/target")


def test_tide_off_disarms_it(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(1, 9, 10)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    turn.pay_the_price("obvious")
    run_command(turn, "/tide")
    assert turn.campaign.tide_armed
    run_command(turn, "/tide off")
    assert not turn.campaign.tide_armed


def test_asset_lists_owned_assets(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    result = run_command(turn, "/asset")
    assert result.lines[0] == "Archer: 1"
    assert result.lines[1] == "Hawk: 2, health 3/3"


def test_asset_catalog_by_category(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    lines = run_command(turn, "/asset list ritual").lines
    assert len(lines) == 17
    assert lines[0] == "augur: Augur"


def test_asset_show(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    lines = run_command(turn, "/asset show archer").lines
    assert lines[0] == "Archer (combat talent). If you wield a bow..."
    assert lines[1].startswith("[x] 1. When you Secure an Advantage")
    assert lines[2].startswith("[ ] 2. Once per fight")


def test_asset_buy_and_upgrade(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.campaign.character.experience = 5
    run_command(turn, "/asset buy owl 3")
    assert turn.campaign.log[-1].text == "Asset: bought Owl for 3 experience"
    run_command(turn, "/asset upgrade owl 1")
    assert turn.campaign.character.asset("owl").marked == [True, False, True]
    assert turn.campaign.character.experience == 0
    assert Campaign.load(tmp_path / "kira.json").character.experience == 0


def test_asset_buy_with_stat_changes(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.campaign.character.experience = 3
    run_command(turn, "/asset buy shadow-kin 1 -heart +shadow +shadow")
    stats = turn.campaign.character.stats
    assert (stats.heart, stats.shadow) == (1, 3)


def test_asset_meter_and_set(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/asset meter hawk health -2")
    assert turn.campaign.log[-1].text == "Asset: Hawk health -2, now 1"
    run_command(turn, "/asset set hawk name Kestrel the Swift")
    assert turn.campaign.character.asset("hawk").fields["name"] == "Kestrel the Swift"
    assert run_command(turn, "/asset").lines[1] == "Hawk (Kestrel the Swift): 2, health 1/3"


def test_asset_discard(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/asset discard hawk")
    assert turn.campaign.character.asset_or_none("hawk") is None


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("/asset buy laser", "no asset"),
        ("/asset buy slayer", "experience"),
        ("/asset upgrade archer", "usage"),
        ("/asset upgrade archer two", "usage"),
        ("/asset buy shadow_kin 1 heart", "stat change"),
        ("/asset meter hawk health", "usage"),
        ("/asset juggle", "usage"),
    ],
)
def test_asset_errors(tmp_path: Path, command: str, message: str):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError, match=message):
        run_command(turn, command)


def test_asset_names_with_spaces(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.campaign.character.experience = 3
    run_command(turn, "/asset buy cave lion 2")
    assert turn.campaign.character.asset("cave_lion").marked == [False, True, False]
    assert run_command(turn, "/asset show animal kin").lines[0].startswith("Animal Kin")


def test_asset_debility(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/asset debility hawk on")
    assert turn.campaign.character.asset("hawk").debility
    assert turn.campaign.log[-1].text == "Asset: Hawk counts as a debility"


def test_asset_harm_owes_companion_endure_harm(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/asset harm hawk 2")
    assert turn.follow_ups == (OwedMove(move="companion_endure_harm", amount=2, asset="hawk"),)
    with pytest.raises(CommandError, match="companion"):
        run_command(turn, "/asset harm archer 2")


def test_endure_owes_endure_harm_or_endure_stress(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/endure harm 2")
    run_command(turn, "/endure stress 1")
    assert turn.follow_ups == (
        OwedMove(move="endure_harm", amount=2),
        OwedMove(move="endure_stress", amount=1),
    )
    assert [entry.text for entry in turn.campaign.log[-2:]] == [
        "Kira faces 2 harm",
        "Kira faces 1 stress",
    ]


@pytest.mark.parametrize("text", ["/endure", "/endure harm", "/endure harm 0", "/endure doom 2"])
def test_endure_needs_harm_or_stress_and_an_amount(tmp_path: Path, text: str):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError):
        run_command(turn, text)
    assert turn.follow_ups == ()


def test_effects_list_and_end(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.campaign.lasting.append(Lasting(kind="talisman_2"))
    turn.campaign.lasting.append(Lasting(kind="pelt", stat="edge"))
    assert run_command(turn, "/effects").lines == ("1 Talisman", "2 Pelt (edge)")
    run_command(turn, "/effects end 1")
    assert turn.campaign.lasting == [Lasting(kind="pelt", stat="edge")]
    assert run_command(turn, "/effects end 1").lines == ()
    assert run_command(turn, "/effects").lines == ("No lasting effects",)


def test_slayer_trophy(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError, match="Slayer"):
        run_command(turn, "/asset use slayer ritual")
    turn.campaign.character.experience = 7
    run_command(turn, "/asset buy slayer")
    run_command(turn, "/asset upgrade slayer 3")
    run_command(turn, "/asset use slayer sojourn")
    assert turn.campaign.lasting == [Lasting(kind="trophy_sojourn")]


def test_lorekeeper_browses_the_archive_once(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.character.experience = 7
    run_command(turn, "/asset buy lorekeeper")
    run_command(turn, "/asset upgrade lorekeeper 3")
    dice.load(2)
    run_command(turn, "/asset use lorekeeper")
    assert turn.campaign.character.stats.wits == 4
    assert "corrupted" in turn.campaign.log[-1].text
    with pytest.raises(CommandError, match="one time"):
        run_command(turn, "/asset use lorekeeper")


def test_an_unknown_vow_error_has_no_extra_quotes(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError) as raised:
        run_command(turn, "/vow mark Nope")
    assert str(raised.value) == "no vow named 'Nope'"
    with pytest.raises(TurnError) as refused:
        turn.make_move("fulfill_your_vow", inputs=MoveInputs(vow="Nope"))
    assert str(refused.value) == "no vow named 'Nope'"


def test_an_unowned_asset_error_has_no_extra_quotes(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(KeyError) as raised:
        turn.campaign.character.asset("owl")
    assert str(raised.value) == "Kira doesn't own owl"


def test_the_asset_usage_puts_stat_changes_after_the_ability(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError) as raised:
        run_command(turn, "/asset juggle")
    assert "buy <asset> [ability [+stat -stat]]" in str(raised.value)
    assert "upgrade <asset> <ability> [+stat -stat]" in str(raised.value)


def test_adjust_momentum_past_minus_six_owes_face_a_setback(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/adjust momentum -10")
    assert turn.campaign.character.momentum == -6
    texts = [entry.text for entry in turn.campaign.log[-2:]]
    assert texts[0] == "Adjust: Momentum is now -6"
    assert texts[1].startswith("Face a Setback: exchange 2 momentum")


def test_asset_commands_take_a_companions_given_name(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/asset set hawk name Kestrel the Swift")
    run_command(turn, "/asset meter kestrel the swift health -1")
    assert turn.campaign.character.asset("hawk").meters["health"] == 2
    assert run_command(turn, "/asset show Kestrel the Swift").lines[0].startswith("Hawk")
    run_command(turn, "/asset harm Kestrel the Swift 1")
    assert turn.follow_ups == (OwedMove(move="companion_endure_harm", amount=1, asset="hawk"),)
