"""The `ironsworn-tui new` command."""

from pathlib import Path

import pytest

from ironsworn_tui import cli
from ironsworn_tui.campaign import Campaign
from ironsworn_tui.creation import AssetPick, Setup
from ironsworn_tui.settings import Settings, SettingsError
from ironsworn_tui.walkthrough import NameStep


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


def _walkthrough_returns(
    monkeypatch: pytest.MonkeyPatch, setup: Setup | None, seen: list[cli.Walkthrough]
) -> None:
    def run(self: cli.Walkthrough) -> Setup | None:
        seen.append(self)
        return setup

    monkeypatch.setattr(cli.Walkthrough, "run", run)


def _name_step(walkthrough: cli.Walkthrough) -> NameStep:
    step = walkthrough.steps[0]
    assert isinstance(step, NameStep)
    return step


def _played(monkeypatch: pytest.MonkeyPatch) -> list[cli.IronswornApp]:
    apps: list[cli.IronswornApp] = []

    def run(self: cli.IronswornApp) -> None:
        apps.append(self)

    monkeypatch.setattr(cli.IronswornApp, "run", run)
    return apps


def _setup(**changes: object) -> Setup:
    setup = Setup(
        name="Blarg",
        description="the Destructor",
        stats={"edge": 2, "heart": 2, "iron": 1, "shadow": 1, "wits": 3},
        assets=[AssetPick("archer"), AssetPick("wayfinder"), AssetPick("hawk", ability=1)],
        background_vow="Find who burned my village",
        inciting_incident="Raiders took my brother.",
        scene="The burned village at dawn",
        vow="Find my brother",
    )
    for key, value in changes.items():
        setattr(setup, key, value)
    return setup


def test_new_alone_runs_the_walkthrough_then_plays(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    seen: list[cli.Walkthrough] = []
    _walkthrough_returns(monkeypatch, _setup(), seen)
    apps = _played(monkeypatch)
    assert cli.main(["new", "--no-model"]) == 0
    assert len(seen) == 1
    path = settings.campaigns_dir / "Blarg.json"
    campaign = Campaign.load(path)
    assert campaign.world.inciting_incident == "Raiders took my brother."
    # In media res, play opens on the Swear an Iron Vow roll.
    assert campaign.pending_card is not None
    assert apps[0].engine.card is not None
    assert apps[0].engine.card.move == "swear_an_iron_vow"
    assert str(path) in capsys.readouterr().out


def test_new_with_a_name_starts_the_walkthrough_with_it(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    seen: list[cli.Walkthrough] = []
    _walkthrough_returns(monkeypatch, None, seen)
    assert cli.main(["new", "Blarg", "--no-model"]) == 1
    assert _name_step(seen[0]).start_name == "Blarg"


def test_quitting_the_walkthrough_saves_nothing(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _walkthrough_returns(monkeypatch, None, [])
    apps = _played(monkeypatch)
    assert cli.main(["new", "--no-model"]) == 1
    assert not settings.campaigns_dir.exists()
    assert apps == []
    assert "Nothing saved" in capsys.readouterr().err


def test_the_walkthrough_knows_the_names_in_use(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    assert cli.main(ARGS) == 0
    seen: list[cli.Walkthrough] = []
    _walkthrough_returns(monkeypatch, None, seen)
    cli.main(["new", "--no-model"])
    assert _name_step(seen[0]).taken("Kira")
    assert not _name_step(seen[0]).taken("Blarg")


def test_overwrite_lets_the_walkthrough_reuse_a_name(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    assert cli.main(ARGS) == 0
    seen: list[cli.Walkthrough] = []
    _walkthrough_returns(monkeypatch, None, seen)
    cli.main(["new", "--overwrite", "--no-model"])
    assert not _name_step(seen[0]).taken("Kira")


def test_a_prologue_opens_play_without_a_roll(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    _walkthrough_returns(monkeypatch, _setup(start="prologue", vow=""), [])
    apps = _played(monkeypatch)
    assert cli.main(["new", "--no-model"]) == 0
    assert apps[0].engine.card is None


def test_new_needs_every_creation_option_or_none(
    settings: Settings, capsys: pytest.CaptureFixture[str]
):
    assert cli.main(["new", "Kira", "--description", "a hunter"]) == 2
    error = capsys.readouterr().err
    assert "--stats, --assets, and --vow" in error


def test_new_with_options_needs_a_name(settings: Settings, capsys: pytest.CaptureFixture[str]):
    assert cli.main(ARGS[:1] + ARGS[2:]) == 2
    assert "name" in capsys.readouterr().err


def test_walkthrough_options_need_the_walkthrough(
    settings: Settings, capsys: pytest.CaptureFixture[str]
):
    assert cli.main(["new", "--bond", "Highvale"]) == 2
    assert "--description" in capsys.readouterr().err


def test_new_refuses_a_background_vow_below_extreme(
    settings: Settings, capsys: pytest.CaptureFixture[str]
):
    assert cli.main([*ARGS, "--rank", "dangerous"]) == 2
