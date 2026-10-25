"""The app's settings file."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ironsworn_tui.settings import load_settings


def test_defaults_when_the_file_is_empty(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_text("")
    settings = load_settings(path)
    assert settings.jevtester_project == Path.home() / "repos" / "jevtester"
    assert settings.target == "decision-1@foundry"
    assert settings.campaigns_dir == tmp_path / "campaigns"
    assert settings.jevtester_config == tmp_path / "jevtester.toml"


def test_values_from_the_file(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_text(
        'jevtester_project = "elsewhere/jevtester"\n'
        'target = "clef-flash@workers-ai"\n'
        'campaigns_dir = "/var/campaigns"\n'
    )
    settings = load_settings(path)
    assert settings.jevtester_project == tmp_path / "elsewhere" / "jevtester"
    assert settings.target == "clef-flash@workers-ai"
    assert settings.campaigns_dir == Path("/var/campaigns")


def test_unknown_keys_rejected(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_text('targett = "x"\n')
    with pytest.raises(ValidationError):
        load_settings(path)


def test_jevtester_config_is_not_a_setting(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_text('jevtester_config = "other.toml"\n')
    with pytest.raises(ValueError, match="jevtester_config"):
        load_settings(path)


def test_repository_settings_file_loads():
    root = Path(__file__).resolve().parent.parent
    settings = load_settings(root / "ironsworn-tui.toml")
    assert settings.jevtester_config == root / "jevtester.toml"
    assert settings.jevtester_config.exists()
