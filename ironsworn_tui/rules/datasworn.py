"""The vendored Datasworn data, indexed by id."""

import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
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


type Stat = Literal["edge", "heart", "iron", "shadow", "wits"]
type ConditionMeter = Literal["health", "spirit", "supply"]
type RollType = Literal["action_roll", "progress_roll", "special_track", "no_roll"]


class _StrictModel(_Model):
    """A model that rejects keys it doesn't declare, so a renamed Datasworn key fails to load."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class StatOption(_StrictModel):
    """A roll with a stat."""

    using: Literal["stat"]
    stat: Stat


class ConditionMeterOption(_StrictModel):
    """A roll with a condition meter, such as Make Camp's supply."""

    using: Literal["condition_meter"]
    condition_meter: ConditionMeter


class ProgressTrackOption(_StrictModel):
    """A progress roll on the move's track.

    [`Move`][ironsworn_tui.rules.datasworn.Move]'s `tracks` names the kind of track.
    """

    using: Literal["progress_track"]


class BondsTrackOption(_StrictModel):
    """A roll on the bonds track, as Write Your Epilogue makes."""

    using: Literal["bonds_track"]


class AssetControlOption(_StrictModel):
    """A roll with an asset's control, such as a companion's health.

    Attributes:
        control: The control, such as `health`.
        assets: Patterns for the assets that have the control, such as `asset:*/companion/*`.
    """

    using: Literal["asset_control"]
    control: str
    assets: tuple[str, ...]


type RollOption = Annotated[
    StatOption | ConditionMeterOption | ProgressTrackOption | BondsTrackOption | AssetControlOption,
    Field(discriminator="using"),
]


class Condition(_StrictModel):
    """One way a move can be rolled, such as Face Danger "With speed, agility, or precision".

    Attributes:
        text: The approach, or None for a move with one way to roll.
        method: How to pick among the roll options. `player_choice` means the player picks
            this condition; `lowest` and `highest` roll the lowest or highest of its options.
            Progress rolls have no method.
        roll_options: The values this condition rolls with.
    """

    text: str | None = None
    method: Literal["player_choice", "lowest", "highest"] | None = None
    roll_options: tuple[RollOption, ...]


class Trigger(_StrictModel):
    """What triggers a move.

    Attributes:
        text: The trigger, such as "When you attempt something risky...".
        conditions: The ways the move can be rolled. Moves with no roll have none.
    """

    text: str
    conditions: tuple[Condition, ...] = ()


class Outcome(_StrictModel):
    """One result of a move.

    Attributes:
        text: The result's text, in Markdown with `datasworn:` links.
    """

    text: str


class Outcomes(_StrictModel):
    """The text of a move's three results."""

    strong_hit: Outcome
    weak_hit: Outcome
    miss: Outcome


class TrackRef(_StrictModel):
    """The kind of progress track a progress move rolls on."""

    category: Literal["Journey", "Combat", "Vow"]


class Move(_StrictModel):
    """A move.

    Attributes:
        id: The move id, such as `face_danger`.
        category: The move category id, such as `adventure`.
        name: The move name, such as "Face Danger".
        roll_type: How the move is rolled.
        trigger: What triggers it.
        text: The full move text, in Markdown with `datasworn:` links.
        outcomes: The text for each result. A move has outcomes exactly when it rolls.
        tracks: The kind of track a progress move rolls on, or None for other moves.
    """

    id: str
    category: str
    name: str
    roll_type: RollType
    trigger: Trigger
    text: str
    outcomes: Outcomes | None = None
    tracks: TrackRef | None = None

    @model_validator(mode="after")
    def _outcomes_match_roll_type(self) -> Move:
        if (self.outcomes is None) != (self.roll_type == "no_roll"):
            raise ValueError(
                f"{self.id} has roll type {self.roll_type} but outcomes {self.outcomes}"
            )
        if (self.tracks is None) == (self.roll_type == "progress_roll"):
            raise ValueError(f"{self.id} has roll type {self.roll_type} but tracks {self.tracks}")
        return self


# Move keys the app doesn't use. `oracles` are indexed with the other oracle tables.
_UNUSED_MOVE_KEYS = {"type", "_source", "oracles"}


@dataclass(frozen=True)
class Datasworn:
    """Flat indices over the Datasworn YAML.

    Move, asset, and NPC ids are leaf names, such as `face_danger`. Oracle ids are the full
    namespaced form, such as `classic/action_and_theme/action`, or
    `classic/fate/pay_the_price/pay_the_price` for a table inside a move.

    The indices are read-only, because one cached instance is shared.

    Attributes:
        moves: Each move, by move id.
        oracles: Each rollable oracle table, by oracle id.
        assets: Each asset's YAML, by asset id.
        npcs: Each NPC's YAML, by NPC id.
        rules: The ruleset's `rules` section.
    """

    moves: Mapping[str, Move]
    oracles: Mapping[str, OracleTable]
    assets: Mapping[str, YamlMap]
    npcs: Mapping[str, YamlMap]
    rules: YamlMap

    def move(self, move_id: str) -> Move:
        """Return a move.

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
    moves: dict[str, Move] = {}
    oracles: dict[str, OracleTable] = {}
    for category_id, category in _load(directory / "moves.yaml")["moves"].items():
        for move_id, move in category["contents"].items():
            fields = {key: value for key, value in move.items() if key not in _UNUSED_MOVE_KEYS}
            moves[move_id] = Move.model_validate({**fields, "id": move_id, "category": category_id})
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
        oracles=MappingProxyType(oracles),
        assets=MappingProxyType(assets),
        npcs=MappingProxyType(npcs),
        rules=_load(directory / "rules.yaml")["rules"],
    )


@cache
def datasworn() -> Datasworn:
    """Return the vendored Datasworn data, loaded once."""
    return load_datasworn()
