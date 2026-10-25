"""The `ironsworn-tui new` command."""

from pathlib import Path

import pytest

from ironsworn_tui import cli
from ironsworn_tui.campaign import Campaign
from ironsworn_tui.settings import Settings, SettingsError


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
    "archer,hawk:2,wright",
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


def test_new_records_background_bonds(settings: Settings):
    assert cli.main([*ARGS, "--bond", "My sister Ash", "--bond", "Highvale"]) == 0
    campaign = Campaign.load(settings.campaigns_dir / "Kira.json")
    assert campaign.bonds == 2
    assert [entry.text for entry in campaign.log] == ["Bond: My sister Ash", "Bond: Highvale"]


def test_new_refuses_more_than_three_bonds(settings: Settings):
    bonds = [arg for name in "abcd" for arg in ("--bond", name)]
    assert cli.main([*ARGS, *bonds]) == 2
    assert not (settings.campaigns_dir / "Kira.json").exists()


def test_new_refuses_the_same_asset_twice(settings: Settings):
    args = [*ARGS]
    args[7] = "archer,archer,wright"
    assert cli.main(args) == 2


def test_a_bad_settings_file_is_an_error_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    def broken() -> Settings:
        raise SettingsError("ironsworn-tui.toml: targett isn't a setting")

    monkeypatch.setattr(cli, "load_settings", broken)
    assert cli.main(["play", "Kira", "--no-model"]) == 2
    assert capsys.readouterr().err == "Error: ironsworn-tui.toml: targett isn't a setting\n"


def test_new_takes_stats_with_spaces_and_capitals(settings: Settings):
    args = [*ARGS]
    args[5] = "Edge=2, Heart=2, iron=1, shadow=1, wits=3"
    assert cli.main(args) == 0


def test_new_explains_bad_stats_plainly(settings: Settings, capsys: pytest.CaptureFixture[str]):
    args = [*ARGS]
    args[5] = "edge=3,heart=3,iron=3,shadow=3,wits=3"
    assert cli.main(args) == 2
    error = capsys.readouterr().err
    assert "3, 2, 2, 1, and 1" in error
    assert "{" not in error


def test_new_suggests_an_asset_for_a_typo(settings: Settings, capsys: pytest.CaptureFixture[str]):
    args = [*ARGS]
    args[7] = "archer,hawk:2,wrigt"
    assert cli.main(args) == 2
    assert "Did you mean wright?" in capsys.readouterr().err


def test_new_lists_the_assets_for_an_unknown_one(
    settings: Settings, capsys: pytest.CaptureFixture[str]
):
    args = [*ARGS]
    args[7] = "archer,hawk:2,zzzz"
    assert cli.main(args) == 2
    error = capsys.readouterr().err
    assert "Companion: cave_lion" in error
    assert "swordmaster" in error


def test_new_says_how_to_start_over(settings: Settings, capsys: pytest.CaptureFixture[str]):
    assert cli.main(ARGS) == 0
    assert cli.main(ARGS) == 2
    error = capsys.readouterr().err
    assert "a campaign named Kira already exists" in error
    assert "--overwrite" in error


def test_new_overwrite_starts_over(settings: Settings):
    assert cli.main(ARGS) == 0
    args = [*ARGS, "--overwrite"]
    args[-2] = "Find my brother"
    assert cli.main(args) == 0
    campaign = Campaign.load(settings.campaigns_dir / "Kira.json")
    assert campaign.vows[0].name == "Find my brother"


def test_new_assets_help_lists_the_ids(settings: Settings, capsys: pytest.CaptureFixture[str]):
    args = [*ARGS]
    args[5] = "x"
    args[7] = "help"
    assert cli.main(args) == 0
    assert "Companion: cave_lion" in capsys.readouterr().out
    assert not (settings.campaigns_dir / "Kira.json").exists()
