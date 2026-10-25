"""The Textual app, driven with its pilot and a fixture decision."""

import asyncio
from pathlib import Path

from textual.pilot import Pilot
from textual.widgets import Input

from ironsworn_tui.app import CharacterPanel, InputsScreen, IronswornApp, SuggestionBar
from ironsworn_tui.campaign import Campaign
from ironsworn_tui.decide import DecideError, Decision, JsonObject
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs
from tests.support import engine


async def settle(app: IronswornApp, pilot: Pilot[None]) -> None:
    """Wait for the decision worker to finish and the screen to update."""
    for _ in range(200):
        await pilot.pause()
        if app.bar_state.mode != "thinking":
            return
    raise AssertionError("the decision worker didn't finish")


def test_a_turn_from_typing_to_an_applied_outcome(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.answers.append(("face_danger", "edge", 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I leap the gap", "enter")
            await settle(app, pilot)
            assert isinstance(app.focused, SuggestionBar)
            assert app.bar_state.mode == "suggest"
            assert app.bar_state.options == ("face_danger",)
            assert app.bar_state.stat == "edge"
            # Edge 2 + 3 = 5 against 4 and 6: a weak hit with a choice of costs.
            dice.load(3, 4, 6)
            await pilot.press("enter")
            assert app.bar_state.mode == "card"
            assert "weak hit" in app.render_bar()
            await pilot.press("4", "enter")
            await pilot.pause()
            assert app.bar_state.mode == "idle"
            assert isinstance(app.focused, Input)

    asyncio.run(play())
    assert turn.campaign.character.supply == 4
    assert Campaign.load(tmp_path / "kira.json").character.supply == 4
    assert decider.requests[0]["state"]["player_says"] == "I leap the gap"


def test_a_command_from_the_input_line(tmp_path: Path):
    turn, _, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"/adjust health -2", "enter")
            await pilot.pause()
            panel = app.query_one(CharacterPanel)
            assert "Health 3" in str(panel.render())

    asyncio.run(play())
    assert turn.campaign.character.health == 3


def test_a_miss_leads_to_pay_the_price(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.answers.append(("face_danger", "iron", 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I shove the door", "enter")
            await settle(app, pilot)
            dice.load(1, 9, 10)
            await pilot.press("enter")
            await pilot.press("enter")
            assert app.bar_state.mode == "follow_up"
            assert "Pay the Price" in app.render_bar()
            dice.load(45)
            await pilot.press("t")
            await pilot.pause()
            assert app.bar_state.mode == "idle"

    asyncio.run(play())
    assert turn.follow_ups == ()
    assert "A new danger or foe is revealed." in turn.campaign.log[-1].text


def test_a_move_that_needs_inputs_asks_for_them(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.answers.append(("enter_the_fray", "shadow", 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I jump them", "enter")
            await settle(app, pilot)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, InputsScreen)
            dice.load(6, 1, 1)
            await pilot.press(*"Raider dangerous", "enter")
            await pilot.pause()
            assert app.bar_state.mode == "card"
            await pilot.press("enter")
            assert app.bar_state.mode == "idle"

    asyncio.run(play())
    assert turn.card is None
    assert [foe.name for foe in turn.campaign.foes] == ["Raider"]
    assert turn.campaign.character.momentum == 4


def test_escape_returns_to_the_input_line(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    decider.answers.append(("no_move", None, 0.9))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I eat", "enter")
            await settle(app, pilot)
            assert app.bar_state.message == "No move"
            await pilot.press("escape")
            assert app.bar_state.mode == "idle"
            assert isinstance(app.focused, Input)

    asyncio.run(play())


def test_stat_and_add_keys_change_the_roll(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.answers.append(("face_danger", "edge", 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I leap", "enter")
            await settle(app, pilot)
            await pilot.press("w", "1", "+", "+")
            assert app.bar_state.stat == "wits"
            assert app.bar_state.adds == 2
            dice.load(1, 9, 10)
            await pilot.press("enter")
            card = app.bar_state.card
            assert card is not None
            assert card.rolled_with == "wits"
            assert card.action is not None
            assert card.action.adds == 2

    asyncio.run(play())


def test_keys_typed_while_the_model_thinks_do_not_reach_the_bar(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    decider.answers.append(("face_danger", "edge", 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I leap", "enter")
            assert app.input.disabled or app.bar_state.mode == "suggest"
            await settle(app, pilot)
            assert app.bar_state.stat == "edge"
            assert turn.card is None

    asyncio.run(play())


def test_a_pending_card_comes_back_after_tabbing_away(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.answers.append(("face_danger", "edge", 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I leap", "enter")
            await settle(app, pilot)
            dice.load(3, 4, 6)
            await pilot.press("enter")
            app.input.focus()
            await pilot.press(*"/scene x", "enter")
            await pilot.pause()
            assert app.bar_state.mode == "card"
            assert turn.campaign.situation == ""
            await pilot.press("4", "enter")

    asyncio.run(play())
    assert turn.campaign.character.supply == 4


def test_owed_follow_ups_show_after_a_restart(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(1, 9, 10)
    turn.make_move("face_danger", stat="edge")
    turn.resolve()

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.bar_state.mode == "follow_up"
            await pilot.press("o")
            assert app.bar_state.mode == "idle"

    asyncio.run(play())
    assert turn.follow_ups == ()


def test_burning_momentum_on_the_card(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    turn.campaign.character.momentum = 8
    decider.answers.append(("face_danger", "iron", 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I hold the door", "enter")
            await settle(app, pilot)
            dice.load(1, 5, 7)
            await pilot.press("enter")
            assert "b burn momentum" in app.render_bar()
            await pilot.press("b")
            card = app.bar_state.card
            assert card is not None
            assert card.hit.label == "strong hit"
            await pilot.press("enter")

    asyncio.run(play())
    assert turn.campaign.character.momentum == 3


def test_a_choice_of_two_needs_two_picks(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"/moves", "enter")
            dice.load(6, 1, 1)
            await pilot.press("6", "enter")
            assert "Choose 2:" in app.render_bar()
            await pilot.press("3", "enter")
            await pilot.pause()
            assert app.bar_state.mode == "card"
            await pilot.press("4", "enter")
            assert app.bar_state.mode == "idle"

    asyncio.run(play())
    assert turn.campaign.character.momentum == 3


def test_end_the_fight_from_the_offer(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    dice.load(6, 1, 1)
    turn.make_move("attack", stat="iron")
    turn.resolve()

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.bar_state.mode == "offer"
            dice.load(1, 2)
            await pilot.press("f", "enter")
            await pilot.pause()

    asyncio.run(play())
    assert turn.campaign.foes == []


def test_a_failed_request_shows_the_full_list_and_a_note(tmp_path: Path):
    turn, _, _ = engine(tmp_path)

    class Down:
        def decide(self, request: JsonObject, target: str) -> Decision:
            raise DecideError("jevtester isn't reachable")

    turn.decider = Down()

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I look around", "enter")
            await settle(app, pilot)
            assert app.bar_state.mode == "suggest"
            assert app.bar_state.selected is None
            assert "face_danger" in app.bar_state.options

    asyncio.run(play())
    assert turn.campaign.log[-1].text.startswith("No suggestion")
