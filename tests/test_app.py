"""The Textual app, driven with its pilot and a fixture decision."""

import asyncio
from pathlib import Path

from textual.pilot import Pilot
from textual.widgets import Input, RichLog

from ironsworn_tui.abilities import BoostRef
from ironsworn_tui.app import (
    AbilitiesScreen,
    CharacterPanel,
    CommandInput,
    DiceScreen,
    InputsScreen,
    IronswornApp,
    PickScreen,
    SuggestionBar,
)
from ironsworn_tui.assets import buy, upgrade
from ironsworn_tui.campaign import Campaign, OwedMove
from ironsworn_tui.decide import DecideError, Decision, JsonObject
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, TurnEngine
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


def test_the_idle_hint_points_to_help(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    hint = IronswornApp(turn).render_bar()
    assert "/help" in hint
    assert "Tab complete" in hint


def test_typing_a_slash_shows_the_options_as_ghost_text(tmp_path: Path):
    turn, _, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            line = app.query_one(CommandInput)
            await pilot.press(*"/or")
            assert line.ghost() == " [oracle]"
            await pilot.press("tab")
            assert line.value == "/oracle "
            assert line.ghost().startswith(" [action | theme | ")
            assert line.ghost().endswith("more]")
            await pilot.press("t")
            assert line.ghost().startswith(" [theme | ")
            await pilot.press("tab")
            assert line.value == "/oracle theme "
            assert isinstance(app.focused, CommandInput)

    asyncio.run(play())


def test_arrows_move_the_selection_and_tab_completes_it(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(40)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            line = app.query_one(CommandInput)
            await pilot.press(*"/ask ")
            await pilot.press("down", "down")
            assert line.selected == 2
            await pilot.press("up")
            await pilot.press("tab")
            assert line.value == "/ask likely "
            await pilot.press(*"Is the gate open?", "enter")
            await pilot.pause()

    asyncio.run(play())
    assert turn.campaign.log[-1].text.startswith("Ask (likely): Is the gate open? ")


def test_escape_leaves_completion(tmp_path: Path):
    turn, _, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            line = app.query_one(CommandInput)
            await pilot.press(*"/vow ")
            assert line.ghost()
            await pilot.press("escape")
            assert line.ghost() == ""
            await pilot.press("tab")
            assert line.value == "/vow "
            assert line.ghost().startswith(" [swear")
            await pilot.press("s")
            assert line.ghost() == " [swear | forsake]"

    asyncio.run(play())


def test_text_without_a_slash_has_no_completion(tmp_path: Path):
    turn, _, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            line = app.query_one(CommandInput)
            await pilot.press(*"I wait")
            assert line.ghost() == ""
            await pilot.press("tab")
            assert not isinstance(app.focused, CommandInput)

    asyncio.run(play())


def test_help_shows_in_the_log(tmp_path: Path):
    turn, _, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"/oracle help", "enter")
            await pilot.pause()
            text = "\n".join(line.text for line in app.query_one(RichLog).lines)
            assert "Spark an idea" in text

    asyncio.run(play())
    assert not any("Spark an idea" in entry.text for entry in turn.campaign.log)


def test_the_panel_lists_assets(tmp_path: Path):
    turn, _, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"/asset set hawk name Kestrel", "enter")
            await pilot.pause()
            panel = str(app.query_one(CharacterPanel).render())
            assert "Archer: 1" in panel
            assert "Hawk (Kestrel): 2, health 3/3" in panel

    asyncio.run(play())


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
    assert "A new danger or foe is revealed." in turn.campaign.log[-2].text


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


def test_escape_declines_the_end_the_fight_offer(tmp_path: Path):
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
            await pilot.press("escape")
            await pilot.press(*"/scene A muddy field", "enter")
            await pilot.pause()
            assert app.bar_state.mode == "idle"

    asyncio.run(play())
    assert turn.campaign.end_fight_offered is False


def test_endure_from_the_move_list_shows_the_owed_move(tmp_path: Path):
    turn, _, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"/moves", "enter")
            await pilot.pause()
            assert app.bar_state.mode == "suggest"
            app.input.focus()
            await pilot.press(*"/endure harm 2", "enter")
            await pilot.pause()
            assert app.bar_state.mode == "follow_up"

    asyncio.run(play())


def test_enter_with_nothing_picked_names_the_choice(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    card = turn.make_move("secure_an_advantage", stat="edge")
    assert card is not None
    notes: list[str] = []

    def note(text: str) -> None:
        notes.append(text)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            app.note = note
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(play())
    assert notes == ["Choose one"]


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


def test_n_saves_no_move_and_escape_saves_nothing(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    saved: list[str] = []

    class Sink:
        def add_case(self, suite: str, case: JsonObject) -> None:
            saved.append(case["expected"]["move"]["answer"])

    turn.cases = Sink()
    decider.answers.append(("face_danger", "edge", 0.95))
    decider.answers.append(("face_danger", "edge", 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I sit by the fire", "enter")
            await settle(app, pilot)
            await pilot.press("n")
            assert app.bar_state.mode == "idle"
            await pilot.press(*"Hmm", "enter")
            await settle(app, pilot)
            await pilot.press("escape")
            await pilot.press(*"/moves", "enter")
            dice.load(6, 1, 1)
            await pilot.press("1", "w", "enter")
            assert app.bar_state.mode == "card"

    asyncio.run(play())
    assert saved == ["no_move"]


def test_abilities_from_the_suggestion_bar(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.answers.append(("secure_an_advantage", "edge", 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I take aim", "enter")
            await settle(app, pilot)
            assert "a abilities (4)" in app.render_bar()
            await pilot.press("a")
            await pilot.pause()
            assert isinstance(app.screen, AbilitiesScreen)
            await pilot.press("1", "enter")
            await pilot.pause()
            assert "Archer 1: Trust your instincts" in app.render_bar()
            # Wits 3 + 1 + 4 = 8 against 7 and 9: a weak hit.
            dice.load(4, 7, 9)
            await pilot.press("enter")
            await pilot.pause()
            assert app.bar_state.card is not None
            assert app.bar_state.card.rolled_with == "wits"
            assert app.bar_state.card.boosts == ("Archer 1: Trust your instincts",)

    asyncio.run(play())


def test_reroll_and_late_add_on_the_card(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    character = turn.campaign.character
    character.experience = 4
    upgrade(character, datasworn(), "wright", 2)
    upgrade(character, datasworn(), "archer", 2)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"/moves", "enter")
            await pilot.pause()
            await pilot.press("1", "a")
            await pilot.pause()
            await pilot.press("2", "enter")
            await pilot.pause()
            # Edge 2 + 3 = 5 against 5 and 9: a miss, which the late add makes a weak hit.
            dice.load(3, 5, 9)
            await pilot.press("e", "enter")
            await pilot.pause()
            assert "+ add after rolling" in app.render_bar()
            await pilot.press("+")
            await pilot.pause()
            card = app.bar_state.card
            assert card is not None
            assert card.action is not None
            assert card.action.adds == 1

    asyncio.run(play())


def test_reroll_dice_from_the_card(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    character = turn.campaign.character
    character.experience = 2
    upgrade(character, datasworn(), "archer", 2)
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    dice.load(1, 9, 10)
    turn.make_move("attack", stat="iron", boosts=[BoostRef("archer", 2)])

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            assert "r reroll" in app.render_bar()
            await pilot.press("r")
            await pilot.pause()
            assert isinstance(app.screen, DiceScreen)
            dice.load(6, 1)
            await pilot.press("1", "2", "enter")
            await pilot.pause()
            card = app.bar_state.card
            assert card is not None
            assert card.action is not None
            assert card.action.challenge_dice == (1, 10)

    asyncio.run(play())


def test_sacrificed_shield_skips_the_follow_up(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    character = turn.campaign.character
    character.experience = 5
    buy(character, datasworn(), "shield_bearer")
    upgrade(character, datasworn(), "shield_bearer", 3)
    turn.campaign.follow_ups.append(OwedMove(move="endure_harm", amount=3))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.bar_state.mode == "follow_up"
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("1", "enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.bar_state.mode == "idle"

    asyncio.run(play())
    assert turn.campaign.character.health == 5


def test_abilities_on_the_end_the_fight_offer(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    character = turn.campaign.character
    character.experience = 5
    buy(character, datasworn(), "revenant")
    upgrade(character, datasworn(), "revenant", 3)
    dice.load(6, 1, 1)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    turn.campaign.end_fight_offered = True

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            assert "a abilities (1)" in app.render_bar()
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("1", "enter")
            await pilot.pause()
            dice.load(1, 1)
            await pilot.press("f")
            await pilot.pause()
            card = app.bar_state.card
            assert card is not None
            assert card.boosts == ("Revenant 3: Bring death",)

    asyncio.run(play())


def test_the_picker_takes_letters_after_nine():
    screen = PickScreen("Pick", [str(n) for n in range(12)], [])
    assert screen.key_for(9) == "a"
    assert screen.index_for("b") == 10
    assert screen.index_for("z") is None


def test_companion_harm_from_a_command(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"/asset harm hawk 1", "enter")
            await pilot.pause()
            assert app.bar_state.mode == "follow_up"
            assert "Companion Endure Harm" in app.render_bar()
            dice.load(6, 1, 1)
            await pilot.press("enter")
            await pilot.pause()
            assert app.bar_state.mode == "card"
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(play())
    assert turn.campaign.character.asset("hawk").meters["health"] == 3


def test_heal_a_companion_from_the_form(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.character.asset("hawk").meters["health"] = 1

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"/moves", "enter")
            await pilot.pause()
            await pilot.press("4", "w", "enter")
            await pilot.pause()
            assert isinstance(app.screen, InputsScreen)
            dice.load(6, 1, 1)
            await pilot.press(*"hawk", "enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(play())
    assert turn.campaign.character.asset("hawk").meters["health"] == 3


def test_asset_moves_show_on_the_full_list(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    character = turn.campaign.character
    character.experience = 3
    buy(character, datasworn(), "augur")

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(*"/moves", "enter")
            await pilot.pause()
            assert "Augur" in app.render_bar()
            while app.bar_state.options[app.bar_state.selected or 0] != "augur":
                await pilot.press("down")
            await pilot.pause()
            assert "[reverse]" in app.render_bar()
            await pilot.press("enter")
            await pilot.pause()
            assert turn.card is not None and turn.card.move == "augur"

    asyncio.run(play())


def test_moves_past_the_ninth_take_capital_letters(tmp_path: Path):
    turn, _, _ = engine(tmp_path)

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.press(*"/moves", "enter")
            await pilot.pause()
            options = app.bar_state.options
            assert len(options) > 10
            bar = app.render_bar()
            assert f"A {turn.move_name(options[9])}" in bar
            assert f"B {turn.move_name(options[10])}" in bar
            assert "1-9 A-" in bar
            await pilot.press("B")
            assert app.bar_state.selected == 10
            # Lowercase letters keep their meanings: a stat, not a move.
            await pilot.press("w")
            assert app.bar_state.selected == 10
            assert app.bar_state.stat == "wits"

    asyncio.run(play())


def test_sojourn_asks_about_a_bond(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.answers.append(("sojourn", None, 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I rest in Bleakhold", "enter")
            await settle(app, pilot)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, InputsScreen)
            dice.load(3, 5, 6)
            await pilot.press(*"yes", "enter")
            await pilot.pause()
            assert app.bar_state.mode == "card"

    asyncio.run(play())
    card = turn.card
    assert card is not None
    assert card.action is not None
    assert card.action.adds == 1


def test_a_card_waiting_at_restart_is_shown_again(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(3, 4, 6)
    card = turn.make_move("face_danger", stat="edge")
    path = tmp_path / "kira.json"
    again = TurnEngine(Campaign.load(path), turn.data, dice, turn.thresholds, path=path)

    async def play() -> None:
        app = IronswornApp(again)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.bar_state.mode == "card"
            assert app.bar_state.card == card

    asyncio.run(play())
