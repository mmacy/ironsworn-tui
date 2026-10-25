"""The `ironsworn-tui new` command."""

from pathlib import Path

import pytest

from ironsworn_tui import cli
from ironsworn_tui.campaign import Campaign
from ironsworn_tui.settings import Settings


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    value = Settings(
        jevtester_project=tmp_path,
        target="decision-1@foundry",
        campaigns_dir=tmp_path / "campaigns",
        jevtester_config=tmp_path / "jevtester.toml",
    )
    monkeypatch.setattr(cli, "load_settings", lambda: value)
    return value


ARGS = [
    "new",
    "Kira",
    "--description",
    "a hunter",
    "--stats",
    "edge=2,heart=2,iron=1,shadow=1,wits=3",
    "--assets",
    "archer,hawk,wright",
    "--vow",
    "Avenge my village",
]


def test_new_creates_the_campaign(settings: Settings):
    assert cli.main(ARGS) == 0
    campaign = Campaign.load(settings.campaigns_dir / "Kira.json")
    assert campaign.character.stats.wits == 3
    assert campaign.vows[0].name == "Avenge my village"


def test_new_refuses_bad_stats(settings: Settings):
    args = [*ARGS]
    args[5] = "edge=3,heart=3,iron=1,shadow=1,wits=1"
    assert cli.main(args) == 2


def test_new_refuses_to_overwrite(settings: Settings):
    assert cli.main(ARGS) == 0
    assert cli.main(ARGS) == 2


def test_play_needs_a_campaign(settings: Settings):
    assert cli.main(["play", "Nobody", "--no-model"]) == 2


def test_play_without_the_model_builds_the_app(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    assert cli.main(ARGS) == 0
    ran: list[bool] = []

    def run(self: cli.IronswornApp) -> None:
        ran.append(True)

    monkeypatch.setattr(cli.IronswornApp, "run", run)
    assert cli.main(["play", "Kira", "--no-model"]) == 0
    assert ran == [True]


def test_play_reports_a_broken_campaign(settings: Settings):
    settings.campaigns_dir.mkdir(parents=True)
    (settings.campaigns_dir / "Kira.json").write_text("{")
    assert cli.main(["play", "Kira", "--no-model"]) == 2
