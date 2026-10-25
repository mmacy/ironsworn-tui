"""The app's settings file."""

from pathlib import Path

import pytest

from ironsworn_tui.settings import SettingsError, load_settings


def test_defaults_when_the_file_is_empty(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_text("")
    settings = load_settings(path)
    assert settings.jevtester_project == Path.home() / "repos" / "jevtester"
    assert settings.target == "decision-1@foundry"
    assert settings.campaigns_dir == tmp_path / "campaigns"
    assert settings.jevtester_config == tmp_path / "jevtester.toml"


def test_a_local_jevtester_config_wins(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_text("")
    (tmp_path / "jevtester.local.toml").write_text("")
    assert load_settings(path).jevtester_config == tmp_path / "jevtester.local.toml"


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
    with pytest.raises(SettingsError, match="targett"):
        load_settings(path)


def test_invalid_toml_rejected(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_text("target = \n")
    with pytest.raises(SettingsError, match="isn't valid TOML"):
        load_settings(path)


def test_wrong_type_rejected(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_text("target = 3\n")
    with pytest.raises(SettingsError, match="target"):
        load_settings(path)


def test_non_utf8_file_rejected(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_bytes(b'target = "\xff"\n')
    with pytest.raises(SettingsError, match="UTF-8"):
        load_settings(path)


def test_missing_file_rejected(tmp_path: Path):
    with pytest.raises(SettingsError, match="can't read"):
        load_settings(tmp_path / "ironsworn-tui.toml")


def test_jevtester_config_is_not_a_setting(tmp_path: Path):
    path = tmp_path / "ironsworn-tui.toml"
    path.write_text('jevtester_config = "other.toml"\n')
    with pytest.raises(SettingsError, match="jevtester_config"):
        load_settings(path)


def test_repository_settings_file_loads():
    root = Path(__file__).resolve().parent.parent
    settings = load_settings(root / "ironsworn-tui.toml")
    # A checkout with the user's real account details uses jevtester.local.toml.
    local = root / "jevtester.local.toml"
    assert settings.jevtester_config == (local if local.exists() else root / "jevtester.toml")
    assert settings.jevtester_config.exists()
