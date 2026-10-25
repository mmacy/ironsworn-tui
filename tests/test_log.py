"""The log's record of each turn: what the move is, the roll, the result, the player's picks,
what changed, and what comes next."""

import asyncio
import re
import typing
from pathlib import Path

import pytest
from textual.widgets import RichLog

from ironsworn_tui.app import LOG_STYLES, IronswornApp
from ironsworn_tui.campaign import Campaign, LogKind
from ironsworn_tui.policy import Suggestion
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, TurnEngine, move_purpose
from tests.support import engine

GATHER = (
    "Gather Information is the move for when you search an area, ask questions, conduct an "
    "investigation, or follow a track."
)
STRONG = (
    "On a strong hit, you discover something helpful and specific. The path you must follow "
    "or action you must take to make progress is made clear. Envision what you learn (Ask the "
    "Oracle if unsure), and take +2 momentum."
)
ORACLE = "ask the oracle (/ask likely for yes or no, /oracle action for ideas)."


def entries(turn: TurnEngine, since: int = 0) -> list[tuple[str, str]]:
    return [(entry.kind, entry.text) for entry in turn.campaign.log[since:]]


def test_gather_information_strong_hit_keeps_the_whole_turn(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    before = len(turn.campaign.log)
    # Wits 3 + 6 = 9 against 3 and 4: a strong hit, +2 momentum.
    dice.load(6, 3, 4)
    turn.make_move("gather_information")
    turn.resolve()
    assert entries(turn, before) == [
        ("explain", GATHER),
        ("roll", "Gather Information +wits: 6 + 3 + 0 = 9 vs 3, 4, strong hit"),
        ("outcome", STRONG),
        ("change", "Momentum +2 (now 4)"),
        ("next", f"Next: imagine what you learn and type it, or {ORACLE}"),
    ]


def test_a_move_is_explained_once_per_campaign(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 3, 4)
    turn.make_move("gather_information")
    turn.resolve()
    assert turn.campaign.explained == ["gather_information"]
    loaded = Campaign.load(tmp_path / "kira.json")
    assert loaded.explained == ["gather_information"]
    before = len(turn.campaign.log)
    dice.load(6, 3, 4)
    turn.make_move("gather_information")
    assert [kind for kind, _ in entries(turn, before)] == ["roll"]


def test_a_weak_hit_logs_the_pick_and_the_new_value(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    # Edge 2 + 3 = 5 against 4 and 6: a weak hit, with a choice of costs.
    dice.load(3, 4, 6)
    card = turn.make_move("face_danger", stat="edge")
    assert card is not None
    before = len(turn.campaign.log)
    turn.resolve([[3]])
    logged = entries(turn, before)
    assert logged[0] == ("outcome", card.outcome_text)
    assert ("choice", "Picked: Sacrifice resources") in logged
    assert ("change", "Supply -1 (now 4)") in logged
    assert [kind for kind, _ in logged] == ["outcome", "choice", "change"]


def test_a_miss_says_pay_the_price_comes_next(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    # Iron 1 + 1 = 2 against 9 and 10: a miss.
    dice.load(1, 9, 10)
    turn.make_move("face_danger", stat="iron")
    before = len(turn.campaign.log)
    turn.resolve()
    logged = entries(turn, before)
    assert ("change", "Owed: Pay the Price") in logged
    assert logged[-1] == (
        "next",
        "Next: Pay the Price. Something goes wrong: o picks the most obvious outcome, "
        "a asks the oracle, t rolls on the table.",
    )
    before = len(turn.campaign.log)
    dice.load(45)
    turn.pay_the_price("table")
    logged = entries(turn, before)
    assert logged[0][0] == "explain"
    assert logged[0][1].startswith("Pay the Price is the move for when you suffer the outcome")
    assert logged[-1] == (
        "next",
        "Next: describe what goes wrong and type it. Apply any harm, stress, or loss with "
        "/endure or /adjust.",
    )


def test_endure_harm_logs_the_damage_with_the_new_health(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.endure("endure_harm", 2)
    assert turn.campaign.log[-1].kind == "next"
    assert turn.campaign.log[-1].text.startswith("Next: Endure Harm (2).")
    before = len(turn.campaign.log)
    dice.load(5, 2, 3)
    turn.roll_follow_up()
    logged = entries(turn, before)
    assert ("change", "Health -2 (now 3)") in logged
    roll = next(text for kind, text in logged if kind == "roll")
    assert "lost first" not in roll


def test_new_tracks_progress_and_initiative_are_logged(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    before = len(turn.campaign.log)
    dice.load(5, 3, 4)
    turn.make_move(
        "swear_an_iron_vow", inputs=MoveInputs(vow="Find my brother", rank=Rank.DANGEROUS)
    )
    assert ("change", "New vow: Find my brother (dangerous)") in entries(turn, before)
    turn.resolve()

    before = len(turn.campaign.log)
    dice.load(6, 2, 5)
    foes = (("Raider", Rank.DANGEROUS),)
    turn.make_move("enter_the_fray", stat="shadow", inputs=MoveInputs(foes=foes))
    turn.resolve()
    logged = entries(turn, before)
    assert ("change", "New foe: Raider (dangerous)") in logged
    assert ("change", "Initiative: Kira has it") in logged

    # Iron 1 + 6 = 7 against 1 and 3: a strong hit, 3 harm against a dangerous foe.
    before = len(turn.campaign.log)
    dice.load(6, 1, 3)
    turn.make_move("attack", stat="iron")
    turn.resolve()
    logged = entries(turn, before)
    assert ("change", "Foe Raider: progress +6 boxes (now 6 boxes)") in logged
    assert logged[-1] == (
        "next",
        "Next: you can End the Fight now. Press f to roll for it, or Esc to keep fighting.",
    )


def test_partial_progress_counts_ticks(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 2, 5)
    foes = (("Wyrm", Rank.EPIC),)
    turn.make_move("enter_the_fray", stat="shadow", inputs=MoveInputs(foes=foes))
    turn.resolve()
    # Iron 1 + 6 = 7 against 1 and 3: a strong hit, 3 harm against an epic foe, 3 ticks.
    before = len(turn.campaign.log)
    dice.load(6, 1, 3)
    turn.make_move("attack", stat="iron")
    turn.resolve()
    assert ("change", "Foe Wyrm: progress +3 ticks (now 3 ticks)") in entries(turn, before)


def test_no_move_says_what_comes_next(tmp_path: Path):
    turn, _, decider = engine(tmp_path)
    decider.answers.append(("no_move", None, 0.9))
    turn.suggest("I share a meal with Ulla.")
    turn.no_move()
    assert entries(turn)[-2:] == [
        ("outcome", "No move"),
        ("next", "Next: no roll is needed. Type what happens, or your next action."),
    ]


def test_accept_logs_why_there_is_no_suggestion(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    turn.decider = None
    suggestion = turn.decide("I look around")
    assert suggestion.note is None
    turn.accept(Suggestion(band="escalate", options=(), decision=None, note="No suggestion: down"))
    assert entries(turn)[-1] == ("note", "No suggestion: down")


@pytest.mark.parametrize(
    ("move", "purpose"),
    [
        (
            "clash",
            "Clash is the move for when your foe has initiative and you fight with them in "
            "close quarters.",
        ),
        ("battle", "Battle is the move for when you fight a battle, and it happens in a blur."),
        ("turn_the_tide", "Turn the Tide: once per fight, when you risk it all."),
        ("endure_harm", "Endure Harm is the move for when you face physical damage."),
        (
            "craft_arrow",
            "Craft Arrow is the move for when you craft a single arrow designated for a "
            "specific foe.",
        ),
    ],
)
def test_move_purpose_reads_as_a_sentence(move: str, purpose: str):
    assert move_purpose(datasworn(), move) == purpose


def test_every_move_has_a_purpose_sentence():
    data = datasworn()
    for move in [*data.moves, *data.asset_moves]:
        purpose = move_purpose(data, move)
        assert purpose.endswith("."), move
        assert "..." not in purpose, move
        assert "](" not in purpose, move


def test_every_log_kind_has_a_style():
    assert set(typing.get_args(LogKind.__value__)) == set(LOG_STYLES)
    styles = [style for style in LOG_STYLES.values() if style]
    assert len(styles) == len(set(styles))


def test_no_text_asks_what_the_player_does():
    root = Path(__file__).resolve().parent.parent / "ironsworn_tui"
    for path in root.glob("*.py"):
        assert not re.search(r"what do(es)? (you|they)\b", path.read_text(), re.IGNORECASE), path


def test_the_log_widget_shows_the_whole_turn(tmp_path: Path):
    turn, dice, decider = engine(tmp_path)
    decider.answers.append(("gather_information", None, 0.95))

    async def play() -> None:
        app = IronswornApp(turn)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"I look around", "enter")
            for _ in range(200):
                await pilot.pause()
                if app.bar_state.mode != "thinking":
                    break
            dice.load(6, 3, 4)
            await pilot.press("enter")
            await pilot.press("enter")
            await pilot.pause()
            shown = "\n".join(line.text for line in app.query_one(RichLog).lines)
            flat = " ".join(shown.split())
            assert "Gather Information is the move for when you search an area" in flat
            assert "discover something helpful and specific" in flat
            assert "Momentum +2 (now 4)" in flat
            assert "Next: imagine what you learn" in flat

    asyncio.run(play())


def test_a_card_with_choices_leaves_out_the_matching_list(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    # Edge 2 + 3 = 5 against 4 and 6: a weak hit, with four costs to choose from.
    dice.load(3, 4, 6)
    card = turn.make_move("face_danger", stat="edge")
    assert card is not None
    assert card.outcome_text == (
        "On a weak hit, you succeed, but face a troublesome cost. Choose one."
    )
    before = len(turn.campaign.log)
    turn.resolve([[3]])
    assert entries(turn, before)[0] == ("outcome", card.outcome_text)


def test_a_list_with_text_after_it_keeps_that_text(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    card = turn.make_move("draw_the_circle", inputs=MoveInputs(foes=(("Rival", Rank.DANGEROUS),)))
    assert card is not None
    assert "*" not in card.outcome_text
    assert "Grant first strike" not in card.outcome_text
    assert card.outcome_text.startswith("On a strong hit, take +1 momentum.")
    assert "\n\nThen, make moves to resolve the fight." in card.outcome_text


def test_a_list_is_left_out_when_a_condition_blocks_some_choices(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    turn.campaign.character.mark_debility("wounded")
    dice.load(6, 1, 1)
    card = turn.make_move("make_camp")
    assert card is not None
    assert "Recuperate" not in card.outcome_text
