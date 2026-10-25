"""The `/` commands."""

from collections.abc import Callable
from pathlib import Path

import pytest

from ironsworn_tui.campaign import Campaign
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
