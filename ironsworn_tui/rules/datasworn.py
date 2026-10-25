"""The vendored Datasworn data, indexed by id."""

import re
import warnings
from collections.abc import Collection, Mapping
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
    """A roll with an asset's meter, such as a companion's health.

    Attributes:
        control: The meter, such as `health`.
        assets: Patterns for the assets that have the meter, such as `asset:*/companion/*`, or
            None in an asset ability, where the meter is the ability's own asset's.
    """

    using: Literal["asset_control"]
    control: str
    assets: tuple[str, ...] | None = None


class AssetOptionRoll(_StrictModel):
    """A roll with the stat an asset's select field names, such as a Devotant's god's stat.

    Attributes:
        option: The select field, such as `stat`.
    """

    using: Literal["asset_option"]
    option: str
    assets: None = None


type RollOption = Annotated[
    StatOption | ConditionMeterOption | ProgressTrackOption | BondsTrackOption | AssetControlOption,
    Field(discriminator="using"),
]

type EnhancementRollOption = Annotated[
    StatOption | ConditionMeterOption | AssetControlOption | AssetOptionRoll,
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


class AssetMeter(_StrictModel):
    """An asset's meter, such as a companion's health or a warband's strength.

    Attributes:
        label: The meter's name, such as `health`.
        max: The highest value.
        value: The value a new asset starts with.
    """

    label: str
    max: int
    value: int


class SelectChoice(_StrictModel):
    """One choice of an asset's select field.

    Attributes:
        label: The choice's name, such as `ghostwood`.
        stat: The stat the choice names, for a field a roll can use.
        counts_as_debility: True when choosing it makes the asset count as a debility, as
            Ironclad's geared for war does.
    """

    label: str
    stat: Stat | None = None
    counts_as_debility: bool = False


class AssetSelect(_StrictModel):
    """An asset's select field, such as a Devotant's god's stat or Ironclad's armor.

    Attributes:
        label: The field's name.
        choices: Each choice, by id.
    """

    label: str
    choices: Mapping[str, SelectChoice]


class By(_StrictModel):
    """Who can make the enhanced move: the character, an ally, or both."""

    player: bool
    ally: bool


class EnhancementCondition(_StrictModel):
    """One condition of an ability's enhancement, such as "by hunting".

    Attributes:
        text: The condition, or None when it only adds a way to roll.
        method: How the condition rolls. `strong_hit` means an automatic strong hit.
        roll_options: The values it lets the move roll with instead.
        by: Who can make the move, or None for the character only.
    """

    text: str | None = None
    method: Literal["player_choice", "highest", "strong_hit"] | None = None
    roll_options: tuple[EnhancementRollOption, ...] = ()
    by: By | None = None


class Enhancement(_StrictModel):
    """How an ability changes some moves.

    Attributes:
        moves: The move ids it enhances, or None for any move whose condition holds.
        roll_type: The kind of roll it enhances.
        conditions: When it applies, and any way to roll it adds.
    """

    moves: tuple[str, ...] | None
    roll_type: RollType
    conditions: tuple[EnhancementCondition, ...] = ()

    @property
    def roll_options(self) -> tuple[EnhancementRollOption, ...]:
        """Every way to roll the enhancement adds, across its conditions."""
        return tuple(option for condition in self.conditions for option in condition.roll_options)


class Ability(_StrictModel):
    """One of an asset's three abilities.

    Attributes:
        name: The ability's name, which some path abilities have.
        text: The ability's text, with links reduced to their labels.
        enabled: True when a new asset starts with it marked.
        enhancements: How it changes moves.
        moves: The moves it adds, such as a ritual's move.
        meter_max: New maximums for the asset's meters, as Awakening's second ability gives.
    """

    name: str | None = None
    text: str
    enabled: bool = False
    enhancements: tuple[Enhancement, ...] = ()
    moves: tuple[Move, ...] = ()
    meter_max: Mapping[str, int] = Field(default_factory=dict[str, int])


class Asset(_StrictModel):
    """An asset.

    Attributes:
        id: The asset id, such as `archer`.
        category: `Combat Talent`, `Companion`, `Path`, or `Ritual`.
        name: The asset's name.
        requirement: What must hold to use it, such as "If you wield a bow...", or None.
        abilities: The three abilities.
        meters: Its meters, by id.
        selects: Its select fields, by id.
        texts: The ids of its text fields, such as a companion's `name`.
        counts_as_debility: True when owning it counts as a debility, as Oathbreaker does.
    """

    id: str
    category: Literal["Combat Talent", "Companion", "Path", "Ritual"]
    name: str
    requirement: str | None = None
    abilities: tuple[Ability, Ability, Ability]
    meters: Mapping[str, AssetMeter] = Field(default_factory=dict[str, AssetMeter])
    selects: Mapping[str, AssetSelect] = Field(default_factory=dict[str, AssetSelect])
    texts: tuple[str, ...] = ()
    counts_as_debility: bool = False


_LINK = re.compile(r"\[([^\]]+)\]\(datasworn:[^)]+\)")
_BOLD = re.compile(r"__(.+?)__")
_TEMPLATE = re.compile(r"\s*\{\{[^}]*\}\}")


def plain_text(text: str) -> str:
    """Reduce Datasworn's `[label](datasworn:...)` links to their labels, and drop its
    `__bold__` markers and its `{{table>...}}` templates, which embed a table in the text."""
    return _BOLD.sub(r"\1", _LINK.sub(r"\1", _TEMPLATE.sub("", text))).strip()


_BLOCK_BREAK = re.compile(r"\n[ \t]*\n")
_HEADING = re.compile(r"__[^_\n]+__")


def _bullets(block: str) -> int | None:
    """Count the items in a block of `* item` lines, or return None for any other block."""
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if lines and all(line.startswith("* ") for line in lines):
        return len(lines)
    return None


def without_lists(text: str, sizes: Collection[int]) -> str:
    """Drop each bulleted list whose item count is in `sizes` from Datasworn text.

    A list is a run of `* item` blocks, with any `__heading__` blocks between them, so
    Sojourn's three headed lists count as one list of eight items. The roll card uses this to
    leave out a list that it shows as numbered choices.

    Args:
        text: Datasworn text, before [`plain_text`][ironsworn_tui.rules.datasworn.plain_text].
        sizes: The item counts of the lists to drop.

    Returns:
        The text without those lists, or the text unchanged when no list matches.
    """
    blocks = _BLOCK_BREAK.split(text)
    kept: list[str] = []
    run: list[str] = []
    items = 0
    dropped = False

    def end_run() -> None:
        nonlocal items, dropped
        if items and items in sizes:
            dropped = True
        else:
            kept.extend(run)
        run.clear()
        items = 0

    for block in blocks:
        count = _bullets(block)
        if count is not None or _HEADING.fullmatch(block.strip()):
            run.append(block)
            items += count or 0
            continue
        end_run()
        kept.append(block)
    end_run()
    return "\n\n".join(kept) if dropped else text


def _leaf(move_ref: str) -> str:
    """Turn `move:classic/combat/strike` or `asset.ability.move:classic/ritual/augur.0.augur`
    into the leaf move id, `strike` or `augur`."""
    return move_ref.rsplit("/", 1)[-1].rsplit(".", 1)[-1]


def _enhancement(raw: YamlMap) -> Enhancement:
    enhances: list[str] | None = raw.get("enhances")
    trigger: YamlMap = raw.get("trigger") or {}
    conditions = [
        {**condition, "roll_options": condition.get("roll_options") or ()}
        for condition in trigger.get("conditions") or ()
    ]
    return Enhancement(
        moves=None if enhances is None else tuple(_leaf(ref) for ref in enhances),
        roll_type=raw["roll_type"],
        conditions=tuple(EnhancementCondition.model_validate(c) for c in conditions),
    )


def _choice(raw: YamlMap) -> SelectChoice:
    enhance_asset: YamlMap = raw.get("enhance_asset") or {}
    return SelectChoice(
        label=raw["label"],
        stat=raw.get("stat"),
        counts_as_debility=bool(enhance_asset.get("count_as_impact")),
    )


def _select(raw: YamlMap) -> AssetSelect:
    choices = {choice_id: _choice(choice) for choice_id, choice in raw["choices"].items()}
    return AssetSelect(label=raw["label"], choices=choices)


def _asset(asset_id: str, raw: YamlMap) -> Asset:
    """Build an asset model from its YAML."""
    meters: dict[str, AssetMeter] = {}
    selects: dict[str, AssetSelect] = {}
    texts: list[str] = []
    # Kindred's `expertise` is the one field an ability, not the asset, defines.
    fields: YamlMap = {**(raw.get("controls") or {}), **(raw.get("options") or {})}
    for ability in raw["abilities"]:
        fields.update(ability.get("options") or {})
    for field_id, field in fields.items():
        match field["field_type"]:
            case "condition_meter":
                meters[field_id] = AssetMeter(
                    label=field["label"], max=field["max"], value=field["value"]
                )
            case "select_value" | "select_enhancement":
                selects[field_id] = _select(field)
            case "text":
                texts.append(field_id)
            case other:
                raise ValueError(f"{asset_id} has a field of unknown type {other}")
    abilities: list[Ability] = []
    for ability in raw["abilities"]:
        asset_moves: YamlMap = ability.get("moves") or {}
        enhance_asset: YamlMap = ability.get("enhance_asset") or {}
        controls: YamlMap = enhance_asset.get("controls") or {}
        abilities.append(
            Ability(
                name=ability.get("name"),
                text=plain_text(ability["text"]),
                enabled=bool(ability.get("enabled")),
                enhancements=tuple(_enhancement(e) for e in ability.get("enhance_moves") or ()),
                moves=tuple(
                    Move.model_validate(
                        {
                            **{k: v for k, v in move.items() if k not in _UNUSED_MOVE_KEYS},
                            "id": move_id,
                            "category": "asset",
                        }
                    )
                    for move_id, move in asset_moves.items()
                ),
                meter_max={meter: control["max"] for meter, control in controls.items()},
            )
        )
    return Asset(
        id=asset_id,
        category=raw["category"],
        name=raw["name"],
        requirement=raw.get("requirement"),
        abilities=(abilities[0], abilities[1], abilities[2]),
        meters=meters,
        selects=selects,
        texts=tuple(texts),
        counts_as_debility=bool(raw.get("count_as_impact")),
    )


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
        assets: Each asset, by asset id.
        asset_moves: Each move an asset ability adds, such as a ritual's, by move id. These
            aren't in `moves`, which the decision model's questions are built from.
        npcs: Each NPC's YAML, by NPC id.
        rules: The ruleset's `rules` section.
    """

    moves: Mapping[str, Move]
    oracles: Mapping[str, OracleTable]
    assets: Mapping[str, Asset]
    asset_moves: Mapping[str, Move]
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

    def asset(self, asset_id: str) -> Asset:
        """Return an asset.

        Raises:
            UnknownIdError: If no asset has the id.
        """
        return _lookup(self.assets, asset_id, "asset")

    def asset_move(self, move_id: str) -> Move:
        """Return a move an asset ability adds.

        Raises:
            UnknownIdError: If no asset move has the id.
        """
        return _lookup(self.asset_moves, move_id, "asset move")

    def find_move(self, move_id: str) -> Move:
        """Return a core move or a move an asset ability adds.

        Raises:
            UnknownIdError: If no move has the id.
        """
        if move_id in self.moves:
            return self.moves[move_id]
        return self.asset_move(move_id)

    def asset_for_move(self, move_id: str) -> str:
        """Return the id of the asset whose ability adds a move.

        Raises:
            UnknownIdError: If no asset move has the id.
        """
        self.asset_move(move_id)
        return next(
            asset.id
            for asset in self.assets.values()
            if any(move.id == move_id for ability in asset.abilities for move in ability.moves)
        )

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
        ValueError: If two assets, two NPCs, or two moves share an id.
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

    raw_assets: dict[str, YamlMap] = {}
    for path in sorted((directory / "assets").glob("*.yaml")):
        for category in _load(path)["assets"].values():
            _add_all(raw_assets, category["contents"], "asset")
    assets = {asset_id: _asset(asset_id, raw) for asset_id, raw in raw_assets.items()}
    asset_moves: dict[str, Move] = {}
    for asset in assets.values():
        for ability in asset.abilities:
            for move in ability.moves:
                if move.id in asset_moves or move.id in moves:
                    raise ValueError(f"two moves have the id {move.id}")
                asset_moves[move.id] = move

    npcs: dict[str, YamlMap] = {}
    for category in _load(directory / "npcs.yaml")["npcs"].values():
        _add_all(npcs, category["contents"], "NPC")

    return Datasworn(
        moves=MappingProxyType(moves),
        oracles=MappingProxyType(oracles),
        assets=MappingProxyType(assets),
        asset_moves=MappingProxyType(asset_moves),
        npcs=MappingProxyType(npcs),
        rules=_load(directory / "rules.yaml")["rules"],
    )


@cache
def datasworn() -> Datasworn:
    """Return the vendored Datasworn data, loaded once."""
    return load_datasworn()
