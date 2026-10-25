"""The app's settings, from `ironsworn-tui.toml`."""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "ironsworn-tui.toml"


class SettingsError(ValueError):
    """The settings file can't be read or isn't valid."""


class Settings(BaseModel):
    """The app's settings.

    Attributes:
        jevtester_project: The jevtester checkout, which the app runs with `uv run --project`.
        target: The jevtester target that answers the decision questions.
        campaigns_dir: Where campaign JSON files are saved.
        jevtester_config: The jevtester config beside the settings file: `jevtester.local.toml`
            when it exists, which holds the user's own account details and isn't committed,
            and otherwise `jevtester.toml`, which has placeholders.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    jevtester_project: Path
    target: str
    campaigns_dir: Path
    jevtester_config: Path


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def load_settings(path: Path = SETTINGS_FILE) -> Settings:
    """Read the settings file, filling in defaults for missing keys.

    Relative paths are relative to the settings file's folder, and `~` means the home folder.

    Args:
        path: The settings file.

    Returns:
        The settings.

    Raises:
        SettingsError: If the file can't be read, isn't valid TOML, has an unknown key or a
            value of the wrong type, or sets `jevtester_config`.
    """
    try:
        raw: dict[str, Any] = tomllib.loads(path.read_text())
    except OSError as error:
        raise SettingsError(f"can't read {path}: {error.strerror}") from error
    except UnicodeDecodeError as error:
        raise SettingsError(f"{path} isn't UTF-8 text: {error.reason}") from error
    except tomllib.TOMLDecodeError as error:
        raise SettingsError(f"{path} isn't valid TOML: {error}") from error
    # jevtester_config is always the jevtester.toml beside this file, never a setting.
    if "jevtester_config" in raw:
        raise SettingsError(f"{path}: jevtester_config isn't a setting")
    base = path.parent
    defaults = {
        "jevtester_project": "~/repos/jevtester",
        "target": "decision-1@foundry",
        "campaigns_dir": "campaigns",
    }
    values: dict[str, Any] = {**defaults, **raw}
    for key in ("jevtester_project", "campaigns_dir"):
        if isinstance(values[key], str):
            values[key] = _resolve(base, values[key])
    local = base / "jevtester.local.toml"
    values["jevtester_config"] = local if local.exists() else base / "jevtester.toml"
    try:
        return Settings.model_validate(values)
    except ValidationError as error:
        problems = "; ".join(_problem(e["loc"], e["msg"]) for e in error.errors())
        raise SettingsError(f"{path}: {problems}") from error


def _problem(loc: tuple[int | str, ...], message: str) -> str:
    key = ".".join(str(part) for part in loc)
    return (
        f"{key} isn't a setting"
        if message == "Extra inputs are not permitted"
        else f"{key}: {message}"
    )
