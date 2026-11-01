"""The character creation walkthrough, driven with Textual's pilot."""

import asyncio
from collections.abc import Awaitable, Callable

from textual.pilot import Pilot
from textual.widgets import Input, Label

from ironsworn_tui.creation import Setup
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.walkthrough import (
    AssetDetailsStep,
    AssetList,
    AssetsStep,
    BackgroundVowStep,
    BondsStep,
    ChoiceList,
    EquipmentStep,
    IncidentStep,
    NameStep,
    PlaceStep,
    ReviewStep,
    SceneStep,
    StatGrid,
    StatsStep,
    TruthStep,
    Walkthrough,
)
from tests.support import Dice

type Driver = Pilot[Setup | None]
type Drive = Callable[[Walkthrough, Driver], Awaitable[None]]
TRUTHS = len(datasworn().truths)


def run(
    drive: Drive,
    dice: Dice | None = None,
    name: str = "",
    taken: Callable[[str], bool] = lambda _: False,
) -> Walkthrough:
    """Run the walkthrough with a drive function, and return it once the drive is done."""
    app = Walkthrough(datasworn(), dice or Dice(), name=name, taken=taken)

    async def go() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            await drive(app, pilot)
            await pilot.pause()

    asyncio.run(go())
    return app


def error(app: Walkthrough) -> str:
    return str(app.query_one("#error", Label).render())


async def write(app: Walkthrough, pilot: Driver, text: str) -> None:
    """Fill in the focused input and press Enter. Typing each key is slow, so only
    `test_typing_fills_in_an_input` types."""
    focused = app.focused
    assert isinstance(focused, Input)
    focused.value = text
    await pilot.press("enter")


async def name_step(app: Walkthrough, pilot: Driver, name: str = "Blarg") -> None:
    await write(app, pilot, name)
    await write(app, pilot, "the Destructor")


async def stats_step(pilot: Driver) -> None:
    # Edge 2, heart 2, iron 1, shadow 1, wits 3.
    await pilot.press("2", "down", "2", "down", "1", "down", "1", "down", "3", "enter")


async def pick(app: Walkthrough, pilot: Driver, *asset_ids: str) -> None:
    assets = app.query_one(AssetList)
    for asset_id in asset_ids:
        assets.highlighted = assets.get_option_index(asset_id)
        await pilot.press("space")


async def character(app: Walkthrough, pilot: Driver) -> None:
    """Fill in the character steps with Blarg: a hawk named Kestrel, archer, and wayfinder."""
    await name_step(app, pilot)
    await stats_step(pilot)
    await pick(app, pilot, "hawk", "archer", "wayfinder")
    await pilot.press("enter")
    await pilot.press("1", "enter")
    await write(app, pilot, "Kestrel")
    await pilot.press("enter")


async def world(app: Walkthrough, pilot: Driver, dice: Dice) -> None:
    """Choose the first truth, roll the rest, and begin in the Havens at Cinderhome."""
    await pilot.press("1", "enter")
    dice.load(*[50] * (TRUTHS - 1))
    await pilot.press("a")
    await pilot.press("5", "enter")
    await write(app, pilot, "Cinderhome")


async def to_review(app: Walkthrough, pilot: Driver, dice: Dice) -> None:
    await character(app, pilot)
    await world(app, pilot, dice)
    await write(app, pilot, "My village")
    await pilot.press("enter", "enter")
    await write(app, pilot, "Find who burned my village")
    await pilot.press("1", "enter")
    await write(app, pilot, "Raiders took my brother")
    await pilot.press("enter")
    await write(app, pilot, "The burned village at dawn")
    await write(app, pilot, "Find my brother")
    await pilot.press("3", "enter")


def test_the_walkthrough_returns_the_setup():
    dice = Dice()

    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await to_review(app, pilot, dice)
        assert isinstance(app.step, ReviewStep)
        await pilot.press("enter")

    app = run(drive, dice)
    setup = app.return_value
    assert setup is not None
    assert (setup.name, setup.description) == ("Blarg", "the Destructor")
    assert setup.stats == {"edge": 2, "heart": 2, "iron": 1, "shadow": 1, "wits": 3}
    assert [(pick.id, pick.ability, pick.fields) for pick in setup.assets] == [
        ("hawk", 1, {"name": "Kestrel"}),
        ("archer", None, {}),
        ("wayfinder", None, {}),
    ]
    assert setup.harm == 2
    assert setup.truths == {"old_world": 0} | {
        truth_id: 1 for truth_id in list(datasworn().truths)[1:]
    }
    assert (setup.region, setup.place) == ("havens", "Cinderhome")
    assert setup.bonds == ["My village"]
    assert (setup.background_vow, setup.background_rank) == (
        "Find who burned my village",
        Rank.EXTREME,
    )
    assert setup.inciting_incident == "Raiders took my brother"
    assert (setup.start, setup.scene) == ("in_media_res", "The burned village at dawn")
    assert (setup.vow, setup.vow_rank) == ("Find my brother", Rank.FORMIDABLE)


def test_the_review_lists_the_choices():
    dice = Dice()

    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await to_review(app, pilot, dice)
        summary = str(app.query_one("#summary").render())
        assert "Blarg, the Destructor" in summary
        assert "Hawk (Kestrel), ability 1; Archer; Wayfinder" in summary
        assert "Where your story begins: Cinderhome, Havens" in summary
        assert "swearing Find my brother (formidable)" in summary
        assert f"World truths: {TRUTHS} chosen, 0 blank" in summary

    run(drive, dice)


def test_quitting_returns_nothing():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await pilot.press("ctrl+q")

    assert run(drive).return_value is None


def test_a_name_and_a_description_are_needed():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await pilot.press("enter", "enter")
        assert isinstance(app.step, NameStep)
        assert error(app) == "Give your character a name."
        await pilot.press("shift+tab")
        await write(app, pilot, "Blarg")
        await pilot.press("enter")
        assert error(app) == "Write a few words about your character."

    run(drive)


def test_a_name_in_use_is_refused():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await name_step(app, pilot, "Kira")
        assert isinstance(app.step, NameStep)
        assert "already exists" in error(app)

    run(drive, taken=lambda name: name == "Kira")


def test_the_name_starts_filled_in_and_can_be_rolled():
    dice = Dice()

    async def drive(app: Walkthrough, pilot: Driver) -> None:
        assert app.query_one("#name", Input).value == "Blarg"
        dice.load(1, 1)
        await pilot.press("ctrl+r")
        rolled = datasworn().oracle("classic/name/ironlander/a").rows[0].text
        assert app.query_one("#name", Input).value == rolled

    run(drive, dice, name="Blarg")


def test_setting_a_bonus_takes_it_from_another_stat():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await name_step(app, pilot)
        grid = app.query_one(StatGrid)
        await pilot.press("3", "down", "3")
        assert grid.values == {"heart": 3}
        await pilot.press("enter")
        assert isinstance(app.step, StatsStep)
        assert error(app) == "Set every stat. Bonuses left: 2, 2, 1, 1."

    run(drive)


def test_three_assets_and_no_more():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await name_step(app, pilot)
        await stats_step(pilot)
        await pick(app, pilot, "archer", "wayfinder")
        await pilot.press("enter")
        assert isinstance(app.step, AssetsStep)
        assert error(app) == "Pick 3 assets. You have 2."
        await pick(app, pilot, "wright", "hawk")
        assert error(app) == "You have 3 assets. Drop one first."
        assert app.query_one(AssetsStep).picked == ["archer", "wayfinder", "wright"]
        # Space on a picked asset drops it.
        await pick(app, pilot, "wright")
        assert app.query_one(AssetsStep).picked == ["archer", "wayfinder"]

    run(drive)


def test_the_asset_details_step_is_skipped_when_nothing_needs_details():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await name_step(app, pilot)
        await stats_step(pilot)
        await pick(app, pilot, "archer", "wayfinder", "swordmaster")
        await pilot.press("enter")
        assert isinstance(app.step, EquipmentStep)
        await pilot.press("escape")
        assert isinstance(app.step, AssetsStep)

    run(drive)


def test_an_ability_that_changes_stats_cannot_start_marked():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await name_step(app, pilot)
        await stats_step(pilot)
        await pick(app, pilot, "shadow_kin", "archer", "wayfinder")
        await pilot.press("enter")
        assert isinstance(app.step, AssetDetailsStep)
        choices = app.step.query_one(ChoiceList)
        await pilot.press("1")
        assert choices.selected is None
        await pilot.press("down")
        assert choices.selected == 1
        await pilot.press("enter")
        assert isinstance(app.step, EquipmentStep)

    app = run(drive)
    assert app.setup.assets[0].ability == 2


def test_a_select_field_is_needed():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await name_step(app, pilot)
        await stats_step(pilot)
        await pick(app, pilot, "ironclad", "archer", "wayfinder")
        await pilot.press("enter", "enter")
        assert error(app) == "Choose Ironclad's equipped."
        await pilot.press("2", "enter")
        assert isinstance(app.step, EquipmentStep)

    app = run(drive)
    assert app.setup.assets[0].fields == {"equipped": "geared_for_war"}


def test_going_back_keeps_the_answers():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await name_step(app, pilot)
        await pilot.press("escape")
        assert isinstance(app.step, NameStep)
        assert app.query_one("#name", Input).value == "Blarg"
        await pilot.press("enter", "enter")
        assert isinstance(app.step, StatsStep)

    run(drive)


def test_rolling_a_truth_picks_the_option_the_roll_covers():
    dice = Dice()

    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await character(app, pilot)
        assert isinstance(app.step, TruthStep)
        dice.load(90)
        await pilot.press("r")
        assert app.step.query_one(ChoiceList).selected == 2
        assert error(app) == "Rolled 90."
        assert "Quest starter:" in str(app.step.query_one("#starter").render())

    run(drive, dice)


def test_a_truth_needs_a_choice_and_can_be_left_open():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await character(app, pilot)
        await pilot.press("enter")
        assert error(app) == "Choose an option, roll, or leave it blank."
        await pilot.press("4", "enter")
        assert isinstance(app.step, TruthStep)
        assert app.step.truth.id == "iron"

    app = run(drive)
    assert "old_world" not in app.setup.truths


def test_rolling_the_rest_moves_past_the_truths():
    dice = Dice()

    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await character(app, pilot)
        dice.load(*[10] * TRUTHS)
        await pilot.press("a")
        assert isinstance(app.step, PlaceStep)

    app = run(drive, dice)
    assert app.setup.truths == dict.fromkeys(datasworn().truths, 0)


def test_the_place_needs_a_region_and_can_roll_a_name():
    dice = Dice()

    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await character(app, pilot)
        dice.load(*[10] * TRUTHS)
        # Enter moves from the regions to the place, then checks the step.
        await pilot.press("a", "enter", "enter")
        assert error(app) == "Choose the region where your story begins."
        await pilot.press("shift+tab")
        await pilot.press("5", "tab")
        dice.load(1, 1)
        await pilot.press("ctrl+r")
        data = datasworn()
        prefix = data.oracle("classic/settlement/quick_name/prefix").rows[0].text
        suffix = data.oracle("classic/settlement/quick_name/suffix").rows[0].text
        assert app.query_one("#place", Input).value == prefix + suffix
        await pilot.press("enter")
        assert isinstance(app.step, BondsStep)

    run(drive, dice)


def test_the_vow_steps_show_the_quest_starters():
    dice = Dice()

    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await character(app, pilot)
        await world(app, pilot, dice)
        await pilot.press("enter", "enter", "enter")
        assert isinstance(app.step, BackgroundVowStep)
        starters = str(app.step.query_one("#starters").render())
        assert "Quest starters from your world:" in starters
        assert datasworn().regions["havens"].quest_starter in starters
        await pilot.press("enter", "enter")
        assert error(app) == "Write your background vow."

    run(drive, dice)


def test_the_oracle_sparks_an_inciting_incident():
    dice = Dice()

    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await character(app, pilot)
        await world(app, pilot, dice)
        await pilot.press("enter", "enter", "enter")
        await write(app, pilot, "Avenge my village")
        await pilot.press("enter")
        assert isinstance(app.step, IncidentStep)
        dice.load(2, 1)
        await pilot.press("ctrl+r")
        theme = datasworn().oracle("classic/action_and_theme/theme").rows[0].text
        assert str(app.step.query_one("#spark").render()) == f"Oracle: Clash and {theme}"

    run(drive, dice)


def test_a_prologue_needs_no_vow():
    dice = Dice()

    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await character(app, pilot)
        await world(app, pilot, dice)
        await pilot.press("enter", "enter", "enter")
        await write(app, pilot, "Avenge my village")
        await pilot.press("enter")
        await pilot.press("enter")
        assert isinstance(app.step, SceneStep)
        await pilot.press("enter", "enter", "enter", "enter")
        assert error(app) == "Write the vow your character swears."
        await pilot.press("shift+tab", "shift+tab", "shift+tab", "2")
        assert not app.query_one("#vow", Input).display
        await pilot.press("enter", "enter")
        assert isinstance(app.step, ReviewStep)
        assert "Start: the normal world, with a prologue" in str(app.query_one("#summary").render())

    app = run(drive, dice)
    assert (app.setup.start, app.setup.vow) == ("prologue", "")


def test_typing_fills_in_an_input():
    async def drive(app: Walkthrough, pilot: Driver) -> None:
        await pilot.press(*"Blarg", "enter")
        assert app.query_one("#name", Input).value == "Blarg"
        assert app.focused is app.query_one("#description", Input)

    run(drive)
