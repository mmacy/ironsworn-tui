"""The app against the configured target through a real jevtester server."""

import asyncio
import os
import random
from pathlib import Path

import pytest
from textual.pilot import Pilot

from ironsworn_tui.app import IronswornApp
from ironsworn_tui.campaign import new_campaign
from ironsworn_tui.decide import jevtester_server
from ironsworn_tui.policy import load_thresholds
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.settings import load_settings
from ironsworn_tui.turn import TurnEngine
from tests.support import kira

pytestmark = pytest.mark.live


async def settle(app: IronswornApp, pilot: Pilot[None]) -> None:
    for _ in range(600):
        await pilot.pause(0.05)
        if app.bar_state.mode != "thinking":
            return
    raise AssertionError("no answer from the model")


def test_the_model_suggests_a_move_in_the_app(tmp_path: Path):
    settings = load_settings()
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    campaign.situation = "A rockslide has taken out the trail. A narrow ledge runs along the cliff."
    with jevtester_server(settings) as client:
        turn = TurnEngine(
            campaign,
            datasworn(),
            random.Random(1),
            load_thresholds(settings.target),
            decider=client,
            target=settings.target,
        )

        async def play() -> None:
            app = IronswornApp(turn)
            async with app.run_test(size=(120, 36)) as pilot:
                await pilot.press(*"I edge along the ledge", "enter")
                await settle(app, pilot)
                assert app.bar_state.mode == "suggest"
                assert "face_danger" in app.bar_state.options
                screenshot = os.environ.get("IRONSWORN_SCREENSHOT")
                if screenshot:
                    app.save_screenshot(screenshot)

        asyncio.run(play())
