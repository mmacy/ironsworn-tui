"""The vendored Datasworn data, indexed by id."""

import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict
from ruamel.yaml import YAML
from ruamel.yaml.error import ReusedAnchorWarning

from ironsworn_tui.rules.errors import UnknownIdError

DATASWORN_DIR = Path(__file__).resolve().parent.parent / "data" / "datasworn"

type YamlMap = dict[str, Any]

ORACLE_ID_PREFIX = "oracle_rollable:"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class RollRange(_Model):
    """The range of rolls a table row covers."""

    min: int
    max: int


class OracleRollDirective(_Model):
    """A row's instruction to roll again, on its own table or another one.

    Attributes:
        oracle: The table to roll on, or None for the same table. Datasworn writes it with an
            `oracle_rollable:` prefix.
        number_of_rolls: How many times to roll.
        auto: True when Datasworn marks the roll as automatic. Without it, the roll is an
            optional example, such as a landscape feature for a settlement name.
        duplicates: What to do when two rolls land on the same row. `reroll` rolls again, and
            `make_it_worse` keeps both and tells the player to make the result worse.
    """

    oracle: str | None = None
    number_of_rolls: int = 1
    auto: bool = False
    duplicates: Literal["reroll", "make_it_worse"] | None = None

    @property
    def table_id(self) -> str | None:
        """The target table's oracle id without the prefix, or None for the same table."""
        if self.oracle is None:
            return None
        return self.oracle.removeprefix(ORACLE_ID_PREFIX)


class OracleRow(_Model):
    """One row of an oracle table."""

    roll: RollRange | None = None
    text: str = ""
    oracle_rolls: tuple[OracleRollDirective, ...] = ()


class OracleTable(_Model):
    """A rollable oracle table."""

    name: str
    rows: tuple[OracleRow, ...]


@dataclass(frozen=True)
class Datasworn:
    """Flat indices over the Datasworn YAML.

    Move, asset, and NPC ids are leaf names, such as `face_danger`. Oracle ids are the full
    namespaced form, such as `classic/action_and_theme/action`, or
    `classic/fate/pay_the_price/pay_the_price` for a table inside a move.

    The indices are read-only, because one cached instance is shared.

    Attributes:
        moves: Each move's YAML, by move id.
        move_categories: Each move's category id, such as `adventure`, by move id.
        oracles: Each rollable oracle table, by oracle id.
        assets: Each asset's YAML, by asset id.
        npcs: Each NPC's YAML, by NPC id.
        rules: The ruleset's `rules` section.
    """

    moves: Mapping[str, YamlMap]
    move_categories: Mapping[str, str]
    oracles: Mapping[str, OracleTable]
    assets: Mapping[str, YamlMap]
    npcs: Mapping[str, YamlMap]
    rules: YamlMap

    def move(self, move_id: str) -> YamlMap:
        """Return a move's YAML.

        Raises:
            UnknownIdError: If no move has the id.
        """
        return _lookup(self.moves, move_id, "move")

    def oracle(self, oracle_id: str) -> OracleTable:
        """Return an oracle table.

        Raises:
            UnknownIdError: If no oracle table has the id.
        """
        return _lookup(self.oracles, oracle_id, "oracle")

    def asset(self, asset_id: str) -> YamlMap:
        """Return an asset's YAML.

        Raises:
            UnknownIdError: If no asset has the id.
        """
        return _lookup(self.assets, asset_id, "asset")

    def npc(self, npc_id: str) -> YamlMap:
        """Return an NPC's YAML.

        Raises:
            UnknownIdError: If no NPC has the id.
        """
        return _lookup(self.npcs, npc_id, "NPC")


def _lookup[T](index: Mapping[str, T], item_id: str, kind: str) -> T:
    try:
        return index[item_id]
    except KeyError:
        raise UnknownIdError(f"unknown {kind} id: {item_id}") from None


def _load(path: Path) -> YamlMap:
    # ruamel.yaml's `load` has an untyped parameter, so the loader is typed as Any.
    loader: Any = YAML(typ="safe", pure=True)
    # YAML lets a file redefine an anchor, and the Datasworn files do.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ReusedAnchorWarning)
        loaded: YamlMap = loader.load(path)
    return loaded


def _walk_oracles(node: YamlMap, prefix: str, into: dict[str, OracleTable]) -> None:
    """Register every rollable table in an oracle tree.

    Datasworn nests tables under `contents` or `collections`, depending on whether the parent
    holds tables or other collections.
    """
    for key, value in node.items():
        if not isinstance(value, dict):
            continue
        child = cast(YamlMap, value)
        path = f"{prefix}/{key}"
        if "rows" in child:
            into[path] = OracleTable.model_validate(child)
        for nested in ("contents", "collections"):
            if nested in child:
                _walk_oracles(child[nested], path, into)


def _add_all(index: dict[str, YamlMap], items: YamlMap, kind: str) -> None:
    for item_id, item in items.items():
        if item_id in index:
            raise ValueError(f"two {kind}s have the id {item_id}")
        index[item_id] = item


def load_datasworn(directory: Path = DATASWORN_DIR) -> Datasworn:
    """Read the Datasworn YAML in a directory and build the indices.

    Args:
        directory: The folder that holds `moves.yaml`, `npcs.yaml`, `rules.yaml`, and the
            `oracles` and `assets` folders.

    Returns:
        The indices.

    Raises:
        ValueError: If two assets or two NPCs share an id.
    """
    moves: dict[str, YamlMap] = {}
    move_categories: dict[str, str] = {}
    oracles: dict[str, OracleTable] = {}
    for category_id, category in _load(directory / "moves.yaml")["moves"].items():
        for move_id, move in category["contents"].items():
            moves[move_id] = move
            move_categories[move_id] = category_id
            move_oracles: YamlMap = move.get("oracles") or {}
            for table_id, table in move_oracles.items():
                table_key = f"classic/{category_id}/{move_id}/{table_id}"
                oracles[table_key] = OracleTable.model_validate(table)

    for path in sorted((directory / "oracles").glob("*.yaml")):
        _walk_oracles(_load(path)["oracles"], "classic", oracles)

    assets: dict[str, YamlMap] = {}
    for path in sorted((directory / "assets").glob("*.yaml")):
        for category in _load(path)["assets"].values():
            _add_all(assets, category["contents"], "asset")

    npcs: dict[str, YamlMap] = {}
    for category in _load(directory / "npcs.yaml")["npcs"].values():
        _add_all(npcs, category["contents"], "NPC")

    return Datasworn(
        moves=MappingProxyType(moves),
        move_categories=MappingProxyType(move_categories),
        oracles=MappingProxyType(oracles),
        assets=MappingProxyType(assets),
        npcs=MappingProxyType(npcs),
        rules=_load(directory / "rules.yaml")["rules"],
    )


@cache
def datasworn() -> Datasworn:
    """Return the vendored Datasworn data, loaded once."""
    return load_datasworn()
