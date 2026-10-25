"""The app's settings, from `ironsworn-tui.toml`."""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "ironsworn-tui.toml"


class Settings(BaseModel):
    """The app's settings.

    Attributes:
        jevtester_project: The jevtester checkout, which the app runs with `uv run --project`.
        target: The jevtester target that answers the decision questions.
        campaigns_dir: Where campaign JSON files are saved.
        jevtester_config: This repository's `jevtester.toml`, beside the settings file.
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
        OSError: If the file can't be read.
        tomllib.TOMLDecodeError: If the file isn't valid TOML.
        pydantic.ValidationError: If the file has an unknown key or a value of the wrong type.
        ValueError: If the file sets `jevtester_config`.
    """
    raw: dict[str, Any] = tomllib.loads(path.read_text())
    # jevtester_config is always the jevtester.toml beside this file, never a setting.
    if "jevtester_config" in raw:
        raise ValueError(f"{path}: jevtester_config isn't a setting")
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
    values["jevtester_config"] = base / "jevtester.toml"
    return Settings.model_validate(values)
