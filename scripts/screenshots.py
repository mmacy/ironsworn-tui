"""Save SVG screenshots of the app for the docs.

Each screen runs the real app headlessly with Textual's pilot. Loaded dice and a fixture
decider stand in for chance and the decision model, so the script calls no hosted model,
uses no network, and draws the same screens every time. The screens follow Blarg the
Destructor, the character from the tutorial in `docs/getting-started.md`.

Run it from the repository root:

```sh
uv run python -m scripts.screenshots
```

The screenshots go to `docs/images/`.
"""

import asyncio
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from textual.pilot import Pilot

from ironsworn_tui.app import IronswornApp
from ironsworn_tui.campaign import create_character, new_campaign
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, TurnEngine
from tests.support import STATS, Dice, FixtureDecider, engine

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"
SIZE = (120, 36)

type Drive = Callable[[IronswornApp, Pilot[None], Dice, FixtureDecider], Awaitable[None]]
type SetUp = Callable[[TurnEngine, Dice], None]


def blarg(turn: TurnEngine) -> None:
    """Give the engine a new campaign for Blarg, as the tutorial creates them.

    Args:
        turn: The turn engine.
    """
    character = create_character(
        datasworn(), "Blarg", "the Destructor", STATS, ["archer", "wayfinder", "hawk:1"]
    )
    turn.campaign = new_campaign(character, "Find who burned my village", Rank.EPIC)


async def settle(app: IronswornApp, pilot: Pilot[None]) -> None:
    """Wait for the decision worker to finish and the screen to update.

    Args:
        app: The running app.
        pilot: The pilot that drives it.

    Raises:
        RuntimeError: If the worker doesn't finish.
    """
    for _ in range(200):
        await pilot.pause()
        if app.bar_state.mode != "thinking":
            return
    raise RuntimeError("the decision worker didn't finish")


async def type_line(pilot: Pilot[None], text: str) -> None:
    """Type a line on the input line and press Enter.

    Args:
        pilot: The pilot that drives the app.
        text: The text to type.
    """
    await pilot.press(*text, "enter")
    await pilot.pause()


async def press(pilot: Pilot[None], *keys: str) -> None:
    """Press keys and let the screen update.

    Args:
        pilot: The pilot that drives the app.
        keys: The keys to press.
    """
    await pilot.press(*keys)
    await pilot.pause()


async def start(app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider) -> None:
    """The play screen as a new campaign opens it."""


async def swear(app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider) -> None:
    """Swear the tutorial's vow and apply the roll card."""
    # Heart 2 + 3 = 5 against 4 and 6: a weak hit.
    dice.load(3, 4, 6)
    await type_line(pilot, "/vow swear dangerous Free my brother from the raiders")
    await press(pilot, "enter")


async def suggestion(
    app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider
) -> None:
    """The suggestion bar with the model's suggested move and stat."""
    await swear(app, pilot, dice, decider)
    decider.answers.append(("face_danger", "edge", 0.94))
    await type_line(pilot, "I creep across the frozen river toward the raider camp")
    await settle(app, pilot)


async def move_list(
    app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider
) -> None:
    """The full list of moves, opened with `/moves`."""
    await swear(app, pilot, dice, decider)
    await type_line(pilot, "/moves")


async def weak_hit(
    app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider
) -> None:
    """A roll card with a weak hit and a choice of costs."""
    await suggestion(app, pilot, dice, decider)
    # Edge 2 + 3 = 5 against 4 and 6: a weak hit.
    dice.load(3, 4, 6)
    await press(pilot, "enter")


async def pay_the_price(
    app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider
) -> None:
    """The follow-up a miss owes: Pay the Price."""
    await suggestion(app, pilot, dice, decider)
    # Edge 2 + 1 = 3 against 9 and 10: a miss.
    dice.load(1, 9, 10)
    await press(pilot, "enter")
    await press(pilot, "enter")


async def turn_record(
    app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider
) -> None:
    """The log's record of a resolved move: Gather Information on a strong hit."""
    await swear(app, pilot, dice, decider)
    decider.answers.append(("gather_information", None, 0.95))
    await type_line(pilot, "I look around to gain an idea of my surroundings")
    await settle(app, pilot)
    # Wits 3 + 6 = 9 against 3 and 4: a strong hit.
    dice.load(6, 3, 4)
    await press(pilot, "enter")
    await press(pilot, "enter")


async def abilities(
    app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider
) -> None:
    """The abilities picker, opened with `a` on the suggestion bar."""
    await swear(app, pilot, dice, decider)
    decider.answers.append(("secure_an_advantage", "edge", 0.95))
    await type_line(pilot, "I climb the ridge above the camp and nock an arrow")
    await settle(app, pilot)
    await press(pilot, "a")


async def oracle(
    app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider
) -> None:
    """A marked vow, and oracle results in the log from `/ask` and `/oracle`."""
    await swear(app, pilot, dice, decider)
    await type_line(pilot, "/vow mark Free my brother from the raiders")
    dice.load(69)
    await type_line(pilot, "/ask likely")
    dice.load(13, 47)
    await type_line(pilot, "/oracle action")
    await type_line(pilot, "/oracle theme")


def set_up_fight(turn: TurnEngine, dice: Dice) -> None:
    """Start a fight with a raider and land one blow, through the turn engine.

    Args:
        turn: The turn engine.
        dice: The loaded dice.
    """
    turn.set_scene("A raider blocks the path to the camp")
    # Heart 2 + 6 = 8 against 1 and 2: a strong hit, so Blarg has initiative.
    dice.load(6, 1, 2)
    turn.make_move(
        "enter_the_fray", stat="heart", inputs=MoveInputs(foes=(("Raider", Rank.DANGEROUS),))
    )
    turn.resolve()
    # Edge 2 + 4 = 6 against 3 and 8: a weak hit, so the arrow lands and the raider presses in.
    dice.load(4, 3, 8)
    turn.make_move("attack", stat="edge")
    turn.resolve()


async def fight(app: IronswornApp, pilot: Pilot[None], dice: Dice, decider: FixtureDecider) -> None:
    """A fight, with the foe's progress track in the panel and the next attack suggested."""
    decider.answers.append(("attack", "edge", 0.93))
    await type_line(pilot, "I leap back and loose another arrow at the raider")
    await settle(app, pilot)


SCREENS: dict[str, Drive] = {
    "start": start,
    "suggestion": suggestion,
    "move-list": move_list,
    "weak-hit": weak_hit,
    "pay-the-price": pay_the_price,
    "turn-record": turn_record,
    "abilities": abilities,
    "oracle": oracle,
    "fight": fight,
}

# Steps that run through the turn engine before the app starts, by screenshot name.
SETUPS: dict[str, SetUp] = {"fight": set_up_fight}


async def capture(name: str, drive: Drive, folder: Path) -> Path:
    """Run the app on a new campaign for Blarg, drive it, and save a screenshot.

    Args:
        name: The screenshot's file name, without `.svg`.
        drive: The steps that bring the app to the screen.
        folder: Where to keep the campaign file.

    Returns:
        The path of the saved screenshot.
    """
    turn, dice, decider = engine(folder)
    blarg(turn)
    setup = SETUPS.get(name)
    if setup is not None:
        setup(turn, dice)
    app = IronswornApp(turn)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await drive(app, pilot, dice, decider)
        await pilot.pause()
        path = app.save_screenshot(f"{name}.svg", str(IMAGES))
    return Path(path)


async def capture_all() -> None:
    """Save every screenshot in `SCREENS`."""
    IMAGES.mkdir(parents=True, exist_ok=True)
    for name, drive in SCREENS.items():
        with tempfile.TemporaryDirectory() as folder:
            path = await capture(name, drive, Path(folder))
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    asyncio.run(capture_all())
