"""The campaign: the character, vows, bonds, foes, journey, and log, saved as JSON."""

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ironsworn_tui.moves import Context, Initiative
from ironsworn_tui.rules.datasworn import Datasworn, Stat, datasworn
from ironsworn_tui.rules.momentum import MomentumBounds, adjust_momentum, momentum_bounds
from ironsworn_tui.rules.progress import TICKS_PER_BOX, TRACK_TICKS, Rank

SCHEMA_VERSION = 2
METER_MAX = 5
STARTING_STATS = (3, 2, 2, 1, 1)
STARTING_ASSETS = 3
STARTING_MOMENTUM = 2

type Meter = Literal["health", "spirit", "supply"]
type Debility = Literal[
    "wounded",
    "shaken",
    "unprepared",
    "encumbered",
    "maimed",
    "corrupted",
    "cursed",
    "tormented",
]

# A marked condition stops its meter from increasing (rulebook page 37).
CONDITION_FOR: dict[Meter, Debility] = {
    "health": "wounded",
    "spirit": "shaken",
    "supply": "unprepared",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Stats(_Model):
    """The five stats."""

    edge: int = Field(ge=0, le=5)
    heart: int = Field(ge=0, le=5)
    iron: int = Field(ge=0, le=5)
    shadow: int = Field(ge=0, le=5)
    wits: int = Field(ge=0, le=5)

    def value(self, stat: Stat) -> int:
        """Return a stat's value."""
        return {
            "edge": self.edge,
            "heart": self.heart,
            "iron": self.iron,
            "shadow": self.shadow,
            "wits": self.wits,
        }[stat]


class ProgressTrack(_Model):
    """A vow, journey, or foe: a name, a rank, and up to 40 ticks of progress."""

    name: str
    rank: Rank
    ticks: int = Field(default=0, ge=0, le=TRACK_TICKS)

    @property
    def boxes(self) -> int:
        """The number of fully filled boxes, which a progress roll uses."""
        return self.ticks // TICKS_PER_BOX

    def mark(self, times: int = 1) -> None:
        """Mark progress for the rank, `times` times, up to a full track."""
        self.ticks = min(TRACK_TICKS, self.ticks + self.rank.ticks * times)

    def recommit(self) -> None:
        """Clear all but one filled box and raise the rank by one, unless it's epic."""
        self.ticks = TICKS_PER_BOX if self.ticks >= TICKS_PER_BOX else 0
        if self.rank < Rank.EPIC:
            self.rank = Rank(self.rank + 1)


class Foe(ProgressTrack):
    """A foe in the current fight. Its track fills as the character harms it."""

    @property
    def harm(self) -> int:
        """The harm this foe inflicts."""
        return self.rank.harm


class AssetError(ValueError):
    """An asset can't be bought, upgraded, or changed as asked."""


class OwnedAsset(_Model):
    """An asset the character owns.

    Attributes:
        id: The asset id, such as `hawk`.
        marked: Whether each of the three abilities is marked.
        meters: Each meter's value, such as a companion's health.
        fields: Each text or select field the player has filled in, such as a companion's
            name or a Devotant's god's stat. A select field holds the choice id.
        debility: True when the asset counts as a debility, as Oathbreaker does.
        spent: The abilities, from 1 to 3, whose one-time-only boost was used.
    """

    id: str
    marked: list[bool] = Field(min_length=3, max_length=3)
    meters: dict[str, int] = Field(default_factory=dict[str, int])
    fields: dict[str, str] = Field(default_factory=dict[str, str])
    debility: bool = False
    spent: list[int] = Field(default_factory=list[int])

    def counts_as_debility(self) -> bool:
        """True when the asset counts as a debility now, as Commander does at 0 strength."""
        return self.debility or self.meters.get("strength") == 0


def new_owned(data: Datasworn, asset_id: str, ability: int | None) -> OwnedAsset:
    """Make a new asset with its starting abilities marked and its meters full.

    Args:
        data: The Datasworn data.
        asset_id: The asset id.
        ability: An ability to mark, from 1 to 3, for an asset that starts with none
            marked, such as a companion. None for an asset that starts with one.

    Raises:
        UnknownIdError: If no asset has the id.
        AssetError: If an asset with none marked gets no pick, or one with a marked
            ability gets one.
    """
    asset = data.asset(asset_id)
    marked = [ability.enabled for ability in asset.abilities]
    if ability is not None:
        if not 1 <= ability <= len(marked):
            raise AssetError(f"{asset.name}'s abilities are numbered 1 to 3")
        if any(marked):
            raise AssetError(f"{asset.name} already starts with an ability marked")
        marked[ability - 1] = True
    elif not any(marked):
        raise AssetError(f"{asset.name} starts with no ability marked; pick one from 1 to 3")
    return OwnedAsset(
        id=asset_id,
        marked=marked,
        meters={meter_id: meter.value for meter_id, meter in asset.meters.items()},
        debility=asset.counts_as_debility,
    )


def meter_max(data: Datasworn, owned: OwnedAsset, meter: str) -> int:
    """Return an asset meter's maximum, raised by any marked ability, as Awakening's is.

    Raises:
        KeyError: If the asset has no such meter.
    """
    asset = data.asset(owned.id)
    highest = asset.meters[meter].max
    for ability, marked in zip(asset.abilities, owned.marked, strict=True):
        if marked and meter in ability.meter_max:
            highest = ability.meter_max[meter]
    return highest


class Character(_Model):
    """The player's character.

    Attributes:
        harm: The harm the character inflicts: 2 when armed with a deadly weapon such as a
            sword, axe, spear, or bow, and 1 when unarmed or using a simple weapon.
    """

    name: str
    description: str
    stats: Stats
    health: int = Field(default=METER_MAX, ge=0, le=METER_MAX)
    spirit: int = Field(default=METER_MAX, ge=0, le=METER_MAX)
    supply: int = Field(default=METER_MAX, ge=0, le=METER_MAX)
    momentum: int = Field(default=STARTING_MOMENTUM, ge=-6, le=10)
    spirit_max: int = Field(default=METER_MAX, ge=0, le=METER_MAX)
    debilities: list[Debility] = Field(default_factory=list[Debility])
    assets: list[OwnedAsset] = Field(default_factory=list[OwnedAsset])
    experience: int = Field(default=0, ge=0)
    harm: int = Field(default=2, ge=1, le=2)

    def asset(self, asset_id: str) -> OwnedAsset:
        """Return an owned asset.

        Raises:
            KeyError: If the character doesn't own it.
        """
        owned = self.asset_or_none(asset_id)
        if owned is None:
            raise KeyError(f"{self.name} doesn't own {asset_id}")
        return owned

    def asset_or_none(self, asset_id: str) -> OwnedAsset | None:
        """Return an owned asset, or None if the character doesn't own it."""
        return next((owned for owned in self.assets if owned.id == asset_id), None)

    def has_ability(self, asset_id: str, ability: int) -> bool:
        """True when the character owns the asset and has the ability marked, from 1 to 3."""
        owned = self.asset_or_none(asset_id)
        return owned is not None and owned.marked[ability - 1]

    @property
    def bounds(self) -> MomentumBounds:
        """The momentum range and reset for the debilities, counting assets that count as one.

        With Battle-scarred's second ability, maimed doesn't count.
        """
        count = len(self.debilities) + sum(owned.counts_as_debility() for owned in self.assets)
        if "maimed" in self.debilities and self.has_ability("battle_scarred", 2):
            count -= 1
        return momentum_bounds(count)

    @property
    def health_max(self) -> int:
        """The highest health: 5, or 4 with Battle-scarred's second ability."""
        return METER_MAX - self.has_ability("battle_scarred", 2)

    def meter_max(self, meter: Meter) -> int:
        """Return a meter's highest value."""
        return {"health": self.health_max, "spirit": self.spirit_max, "supply": METER_MAX}[meter]

    def meter(self, meter: Meter) -> int:
        """Return a meter's value."""
        return {"health": self.health, "spirit": self.spirit, "supply": self.supply}[meter]

    def change_meter(self, meter: Meter, amount: int) -> int:
        """Add to or take from a meter, within 0 and its maximum.

        A marked condition stops its meter from increasing.

        Returns:
            The change actually made.
        """
        if amount > 0 and CONDITION_FOR[meter] in self.debilities:
            return 0
        before = self.meter(meter)
        after = max(0, min(self.meter_max(meter), before + amount))
        setattr(self, meter, after)
        return after - before

    def change_momentum(self, amount: int) -> int:
        """Add to or take from momentum, within -6 and the maximum.

        Returns:
            The loss past -6, which the player takes with Face a Setback.
        """
        change = adjust_momentum(self.momentum, amount, self.bounds.max)
        self.momentum = change.momentum
        return change.setback

    def reset_momentum(self) -> None:
        """Set momentum to the reset value, as after burning it."""
        self.momentum = self.bounds.reset

    def mark_debility(self, debility: Debility) -> None:
        """Mark a debility, and lower momentum if it's now over the maximum."""
        if debility not in self.debilities:
            self.debilities.append(debility)
            self.momentum = min(self.momentum, self.bounds.max)

    def clear_debility(self, debility: Debility) -> None:
        """Clear a debility if it's marked."""
        if debility in self.debilities:
            self.debilities.remove(debility)


class OwedMove(_Model):
    """A follow-up move a result called for, still to be made.

    Attributes:
        move: The move id, such as `pay_the_price`.
        amount: The harm or stress, for Endure Harm and Endure Stress.
        vow: The vow, for Forsake Your Vow.
    """

    move: str
    amount: int | None = None
    vow: str | None = None


type LogKind = Literal["message", "roll", "outcome", "note", "command"]


class LogEntry(_Model):
    """One line of the log."""

    kind: LogKind
    text: str


class Campaign(_Model):
    """Everything saved about one campaign.

    Attributes:
        schema_version: The file format's version.
        character: The character.
        vows: The active vows.
        bonds: Ticks on the bonds track.
        foes: The foes in the current fight. The fight ends when none are left.
        target: The name of the foe an attack targets.
        journey: The active journey, if any.
        initiative: Who has initiative, or None outside a fight.
        tide_used: True when Turn the Tide has been used in this fight.
        situation: The scene line the player keeps up to date with `/scene`.
        follow_ups: The follow-up moves still owed, in order.
        next_add: The add for the next action roll, from a result such as "Take control".
        tide_armed: True when Turn the Tide is armed for the next move.
        end_fight_offered: True when the last result allows End the Fight.
        fight_uses: The once-per-fight boosts used in this fight, as `asset:ability`.
        background_vow: The name of the background vow, which Fated counts.
        log: The turn log.
    """

    schema_version: Literal[2] = SCHEMA_VERSION
    character: Character
    vows: list[ProgressTrack] = Field(default_factory=list[ProgressTrack])
    bonds: int = Field(default=0, ge=0, le=TRACK_TICKS)
    foes: list[Foe] = Field(default_factory=list[Foe])
    target: str | None = None
    journey: ProgressTrack | None = None
    initiative: Initiative | None = None
    tide_used: bool = False
    situation: str = ""
    follow_ups: list[OwedMove] = Field(default_factory=list[OwedMove])
    next_add: int = 0
    tide_armed: bool = False
    end_fight_offered: bool = False
    fight_uses: list[str] = Field(default_factory=list[str])
    background_vow: str | None = None
    log: list[LogEntry] = Field(default_factory=list[LogEntry])

    @model_validator(mode="after")
    def _background_vow_from_first_vow(self) -> Campaign:
        # Campaigns saved before `background_vow` existed started with the background vow.
        if self.background_vow is None and self.vows:
            self.background_vow = self.vows[0].name
        return self

    @property
    def context(self) -> Context:
        """The context: a fight when foes remain, a journey when one is active."""
        if self.foes:
            return Context.FIGHT
        if self.journey is not None:
            return Context.JOURNEY
        return Context.EXPLORING

    def vow(self, name: str) -> ProgressTrack:
        """Return the active vow with a name.

        Raises:
            KeyError: If no active vow has the name.
        """
        for vow in self.vows:
            if vow.name == name:
                return vow
        raise KeyError(f"no vow named {name!r}")

    def target_foe(self) -> Foe | None:
        """Return the foe an attack targets: the selected one, or the first."""
        for foe in self.foes:
            if foe.name == self.target:
                return foe
        return self.foes[0] if self.foes else None

    def remove_foe(self, foe: Foe) -> None:
        """Take a foe out of the fight, and end the fight when none remain."""
        self.foes.remove(foe)
        if self.target == foe.name:
            self.target = self.foes[0].name if self.foes else None
        if not self.foes:
            self.end_fight()

    def end_fight(self) -> None:
        """End the fight, however it ended: clear the foes, initiative, and Turn the Tide."""
        self.foes = []
        self.target = None
        self.initiative = None
        self.tide_used = False
        self.tide_armed = False
        self.end_fight_offered = False
        self.fight_uses = []

    def add_log(self, kind: LogKind, text: str) -> None:
        """Add a line to the log."""
        self.log.append(LogEntry(kind=kind, text=text))

    def save(self, path: Path) -> None:
        """Write the campaign as JSON, replacing the file only once the write is on disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            file.write(self.model_dump_json(indent=2) + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)

    @classmethod
    def load(cls, path: Path) -> Campaign:
        """Read a campaign from JSON, and check that its parts agree.

        Raises:
            OSError: If the file can't be read.
            pydantic.ValidationError: If the file isn't a valid campaign.
            ValueError: If its parts disagree, such as a target that names no foe.
        """
        campaign = cls.model_validate_json(path.read_text(encoding="utf-8"))
        campaign.check()
        return campaign

    def check(self) -> None:
        """Raise if the campaign's parts disagree.

        Raises:
            ValueError: If a debility is marked twice, momentum or a meter is over its maximum,
                the target names no foe, initiative is set outside a fight or missing in one,
                two foes or two vows share a name, or an asset isn't valid.
        """
        character = self.character
        problems: list[str] = []
        if len(set(character.debilities)) != len(character.debilities):
            problems.append("a debility is marked twice")
        if character.momentum > character.bounds.max:
            problems.append(f"momentum {character.momentum} is over {character.bounds.max}")
        if character.health > character.health_max:
            problems.append(f"health {character.health} is over {character.health_max}")
        if character.spirit > character.spirit_max:
            problems.append(f"spirit {character.spirit} is over {character.spirit_max}")
        problems += _asset_problems(character)
        foe_names = [foe.name for foe in self.foes]
        if self.target is not None and self.target not in foe_names:
            problems.append(f"the target {self.target!r} isn't a foe")
        if (self.initiative is None) != (not self.foes):
            problems.append("initiative must be set exactly when there's a fight")
        if len(set(foe_names)) != len(foe_names):
            problems.append("two foes share a name")
        vow_names = [vow.name for vow in self.vows]
        if len(set(vow_names)) != len(vow_names):
            problems.append("two vows share a name")
        if problems:
            raise ValueError("; ".join(problems))


def _asset_problems(character: Character) -> list[str]:
    data = datasworn()
    problems: list[str] = []
    ids = [owned.id for owned in character.assets]
    if len(set(ids)) != len(ids):
        problems.append("an asset is owned twice")
    for owned in character.assets:
        if owned.id not in data.assets:
            problems.append(f"{owned.id} isn't an asset")
            continue
        asset = data.asset(owned.id)
        enabled = [ability.enabled for ability in asset.abilities]
        if not any(owned.marked) or any(
            e and not m for e, m in zip(enabled, owned.marked, strict=True)
        ):
            problems.append(f"{owned.id} is missing a marked ability")
        if asset.counts_as_debility and not owned.debility:
            problems.append(f"{owned.id} must count as a debility")
        if owned.fields.get("equipped") == "geared_for_war" and (
            "encumbered" not in character.debilities
        ):
            problems.append(f"{owned.id} is geared for war, so encumbered must be marked")
        if set(owned.meters) != set(asset.meters):
            problems.append(f"{owned.id} has meters {sorted(owned.meters)}")
            continue
        for meter, value in owned.meters.items():
            if not 0 <= value <= meter_max(data, owned, meter):
                problems.append(f"{owned.id} {meter} {value} is out of range")
        for field, value in owned.fields.items():
            if field in asset.selects:
                if value not in asset.selects[field].choices:
                    problems.append(f"{owned.id} {field} {value!r} isn't a choice")
            elif field not in asset.texts:
                problems.append(f"{owned.id} has no field {field}")
    return problems


def create_character(
    data: Datasworn,
    name: str,
    description: str,
    stats: dict[Stat, int],
    assets: list[str],
    harm: int = 2,
) -> Character:
    """Create a character from the short creation form.

    Args:
        data: The Datasworn data, to check the asset ids.
        name: The character's name.
        description: A few words about them, such as "a hunter".
        stats: The five stats, assigned from 3, 2, 2, 1, 1.
        assets: Three asset ids. An asset that starts with no ability marked, such as a
            companion, names the ability to mark after a colon, such as `hawk:2`.
        harm: 2 when the character carries a deadly weapon, 1 when not.

    Returns:
        The character, with full meters and +2 momentum.

    Raises:
        ValueError: If the stats aren't 3, 2, 2, 1, 1, or there aren't three assets.
        AssetError: If an asset needs a pick and has none, or has one it can't take.
        UnknownIdError: If an asset id isn't in the data.
    """
    if set(stats) != set(Stats.model_fields) or sorted(stats.values(), reverse=True) != list(
        STARTING_STATS
    ):
        raise ValueError(f"stats must be assigned from {STARTING_STATS}, got {stats}")
    if len(assets) != STARTING_ASSETS:
        raise ValueError(f"pick {STARTING_ASSETS} assets, got {len(assets)}")
    owned: list[OwnedAsset] = []
    for spec in assets:
        asset_id, _, pick = spec.partition(":")
        if pick and not pick.isdigit():
            raise AssetError(f"write a pick as an ability number, such as {asset_id}:1")
        if pick:
            _check_no_stat_change(data, asset_id, int(pick))
        owned.append(new_owned(data, asset_id, int(pick) if pick else None))
    character = Character(
        name=name,
        description=description,
        stats=Stats.model_validate(stats),
        assets=owned,
        harm=harm,
    )
    character.health = character.health_max
    return character


# Abilities whose marking moves stat points, which a new character can't take.
STAT_CHANGE_ABILITIES = {("battle_scarred", 1), ("shadow_kin", 1)}


def _check_no_stat_change(data: Datasworn, asset_id: str, ability: int) -> None:
    if (asset_id, ability) in STAT_CHANGE_ABILITIES:
        name = data.asset(asset_id).name
        raise AssetError(f"buy {name} with /asset buy once you play, to choose its stat changes")


def new_campaign(character: Character, background_vow: str, rank: Rank) -> Campaign:
    """Start a campaign with a character and their background vow."""
    return Campaign(
        character=character,
        vows=[ProgressTrack(name=background_vow, rank=rank)],
        background_vow=background_vow,
    )
