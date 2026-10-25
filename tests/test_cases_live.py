"""Cases from play, saved through a real jevtester server, then run and reported."""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from ironsworn_tui.campaign import new_campaign
from ironsworn_tui.decide import jevtester_server
from ironsworn_tui.policy import load_thresholds
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.settings import Settings, load_settings
from ironsworn_tui.turn import TurnEngine
from tests.support import Dice, kira

pytestmark = pytest.mark.live
ROOT = Path(__file__).resolve().parent.parent


def test_play_cases_can_be_run_and_reported(tmp_path: Path):
    shutil.copy(ROOT / "jevtester.toml", tmp_path / "jevtester.toml")
    shutil.copytree(ROOT / "suites", tmp_path / "suites")
    repo = load_settings()
    settings = Settings(
        jevtester_project=repo.jevtester_project,
        target=repo.target,
        campaigns_dir=tmp_path / "campaigns",
        jevtester_config=tmp_path / "jevtester.toml",
    )
    dice = Dice()
    with jevtester_server(settings) as client:
        turn = TurnEngine(
            new_campaign(kira(), "Avenge my village", Rank.EPIC),
            datasworn(),
            dice,
            load_thresholds(settings.target),
            decider=client,
            target=settings.target,
            cases=client,
        )
        turn.suggest("I edge along the ledge, keeping my weight on the balls of my feet.")
        dice.load(6, 1, 1)
        turn.make_move("face_danger", stat="edge")
        turn.resolve()
        turn.suggest("I search the ruined shrine for any sign of the missing pilgrims.")
        dice.load(6, 1, 1)
        turn.make_move("gather_information")
        turn.resolve()
        turn.suggest("I share a meal with Ulla and we talk about old times.")
        turn.no_move()

    loader: Any = YAML(typ="safe", pure=True)
    suite: dict[str, Any] = loader.load(tmp_path / "suites" / "play-exploring.yaml")
    answers = [case["expected"]["move"]["answer"] for case in suite["cases"]]
    assert answers == ["face_danger", "gather_information", "no_move"]

    command = [
        "uv",
        "run",
        "--project",
        str(settings.jevtester_project),
        "jevtester",
        "--config",
        str(settings.jevtester_config),
    ]
    run = subprocess.run(
        [*command, "run", "play-exploring", "--target", settings.target],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=True,
    )
    match = re.search(r"Run (\w+) finished: 3 jobs", run.stdout)
    assert match, run.stdout
    report = subprocess.run(
        [*command, "report", match.group(1)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=True,
    )
    assert "play-exploring" in report.stdout
    assert "## move" in report.stdout
