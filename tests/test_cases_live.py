"""Cases from play, saved through a real jevtester server, then run and reported."""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from ironsworn_tui.campaign import new_campaign
from ironsworn_tui.cases import ORACLE_SUITE, play_suite_name
from ironsworn_tui.decide import jevtester_server
from ironsworn_tui.experiment import dump_yaml, play_oracle_suite, play_suite
from ironsworn_tui.moves import Context
from ironsworn_tui.policy import load_thresholds
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.settings import Settings, load_settings
from ironsworn_tui.turn import TurnEngine
from tests.support import Dice, kira

pytestmark = pytest.mark.live
ROOT = Path(__file__).resolve().parent.parent


def _scratch_settings(tmp_path: Path) -> Settings:
    """Copy the jevtester config the app uses and the suites, with empty play suites, so the
    cases a test saves are the only ones."""
    repo = load_settings()
    shutil.copy(repo.jevtester_config, tmp_path / "jevtester.toml")
    shutil.copytree(ROOT / "suites", tmp_path / "suites")
    empty = {play_suite_name(context): play_suite(context) for context in Context}
    empty[ORACLE_SUITE] = play_oracle_suite()
    for name, suite in empty.items():
        (tmp_path / "suites" / f"{name}.yaml").write_text(dump_yaml(suite))
    return Settings(
        jevtester_project=repo.jevtester_project,
        target=repo.target,
        campaigns_dir=tmp_path / "campaigns",
        jevtester_config=tmp_path / "jevtester.toml",
    )


def test_an_oracle_question_is_saved_as_a_case(tmp_path: Path):
    settings = _scratch_settings(tmp_path)
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
        suggestion = turn.suggest_oracle("What is the guard called?")
        assert suggestion.band == "act"
        assert suggestion.options[0] == "ironlander-name"
        dice.load(1, 1)
        turn.answer_oracle("ironlander-name", "What is the guard called?")

    loader: Any = YAML(typ="safe", pure=True)
    suite: dict[str, Any] = loader.load(tmp_path / "suites" / f"{ORACLE_SUITE}.yaml")
    [case] = suite["cases"]
    assert case["expected"] == {"kind": {"answer": "table"}, "table": {"answer": "ironlander-name"}}


def test_play_cases_can_be_run_and_reported(tmp_path: Path):
    settings = _scratch_settings(tmp_path)
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
