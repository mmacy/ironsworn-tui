"""Owning assets: buying and upgrading them with experience, their meters, and their fields.

The rulebook's Advance move spends 3 experience on a new asset and 2 on an upgrade. Marking
some abilities changes the character once, such as Shadow-kin's stat points, and this module
applies those changes when the ability is marked.
"""

from ironsworn_tui.campaign import (
    STAT_CHANGE_ABILITIES,
    AssetError,
    Character,
    OwnedAsset,
    meter_max,
    new_owned,
)
from ironsworn_tui.rules.datasworn import Asset, Datasworn, Stat

NEW_ASSET_COST = 3
UPGRADE_COST = 2
STAT_MAX = 4

# Abilities that take 1 experience off assets of one category (rulebook asset cards).
_DISCOUNTS: dict[tuple[str, int], str] = {
    ("animal_kin", 2): "Companion",
    ("ritualist", 3): "Ritual",
    ("weaponmaster", 2): "Combat Talent",
}
# Animal Kin's discount is for an animal or beast companion, and Kindred is a person.
_NOT_ANIMALS = {"kindred"}

type StatChanges = dict[Stat, int]


def owned(character: Character, asset_id: str) -> OwnedAsset:
    """Return an asset the character owns.

    Raises:
        AssetError: If the character doesn't own it.
    """
    found = character.asset_or_none(asset_id)
    if found is None:
        raise AssetError(f"{character.name} doesn't own {asset_id}")
    return found


def cost(character: Character, asset: Asset, base: int) -> int:
    """Return what buying or upgrading an asset costs, after any discount."""
    discounted = any(
        character.has_ability(path, ability)
        and category == asset.category
        and not (path == "animal_kin" and asset.id in _NOT_ANIMALS)
        for (path, ability), category in _DISCOUNTS.items()
    )
    return base - discounted


def buy(
    character: Character,
    data: Datasworn,
    asset_id: str,
    ability: int | None = None,
    changes: StatChanges | None = None,
) -> int:
    """Spend experience on a new asset.

    Args:
        character: The character.
        data: The Datasworn data.
        asset_id: The asset to buy.
        ability: The ability to mark, from 1 to 3, for an asset that starts with none.
        changes: The stat changes the marked ability makes, for Battle-scarred and
            Shadow-kin.

    Returns:
        The experience spent.

    Raises:
        AssetError: If the character already owns it, lacks the experience, or the pick or
            the changes aren't valid. Nothing changes then.
        UnknownIdError: If no asset has the id.
    """
    asset = data.asset(asset_id)
    if character.asset_or_none(asset_id) is not None:
        raise AssetError(f"{character.name} already owns {asset.name}")
    new = new_owned(data, asset_id, ability)
    spent = _spend(character, cost(character, asset, NEW_ASSET_COST))
    marked = [index + 1 for index, mark in enumerate(new.marked) if mark]
    for number in marked:
        _check_changes(character, asset, number, changes or {})
    character.experience -= spent
    character.assets.append(new)
    for number in marked:
        _apply_marking(character, asset_id, number, changes or {})
    return spent


def upgrade(
    character: Character,
    data: Datasworn,
    asset_id: str,
    ability: int,
    changes: StatChanges | None = None,
) -> int:
    """Spend experience to mark one of an owned asset's abilities.

    Args:
        character: The character.
        data: The Datasworn data.
        asset_id: The asset.
        ability: The ability to mark, from 1 to 3.
        changes: The stat changes the ability makes, for Battle-scarred and Shadow-kin.

    Returns:
        The experience spent.

    Raises:
        AssetError: If the character doesn't own the asset, the ability is marked already,
            the character lacks the experience, or the changes aren't valid. Nothing changes
            then.
    """
    target = owned(character, asset_id)
    asset = data.asset(asset_id)
    if not 1 <= ability <= len(target.marked):
        raise AssetError(f"{asset.name}'s abilities are numbered 1 to 3")
    if target.marked[ability - 1]:
        raise AssetError(f"{asset.name}'s ability {ability} is already marked")
    spent = _spend(character, cost(character, asset, UPGRADE_COST))
    _check_changes(character, asset, ability, changes or {})
    character.experience -= spent
    target.marked[ability - 1] = True
    _apply_marking(character, asset_id, ability, changes or {})
    return spent


def _spend(character: Character, amount: int) -> int:
    if character.experience < amount:
        raise AssetError(
            f"that costs {amount} experience, and {character.name} has {character.experience}"
        )
    return amount


def _check_changes(character: Character, asset: Asset, ability: int, changes: StatChanges) -> None:
    """Raise unless the stat changes are what marking the ability calls for."""
    if (asset.id, ability) not in STAT_CHANGE_ABILITIES:
        if changes:
            raise AssetError(f"{asset.name}'s ability {ability} doesn't change a stat")
        return
    lowered: StatChanges = {stat: -amount for stat, amount in changes.items() if amount < 0}
    raised: StatChanges = {stat: amount for stat, amount in changes.items() if amount > 0}
    if asset.id == "shadow_kin":
        # "Reduce your heart stat by 1 and add up to +2 to shadow."
        valid = lowered == {"heart": 1} and set(raised) <= {"shadow"} and sum(raised.values()) <= 2
        rule = "lower heart by 1 and raise shadow by up to 2"
    else:
        # "Reduce your edge or iron by 1 and add +2 to wits or heart, or +1 to each."
        valid = (
            lowered in ({"edge": 1}, {"iron": 1})
            and set(raised) <= {"wits", "heart"}
            and sum(raised.values()) == 2
        )
        rule = "lower edge or iron by 1, and raise wits or heart by 2, or each by 1"
    if not valid:
        raise AssetError(f"{asset.name}: {rule}")
    for stat, amount in raised.items():
        if character.stats.value(stat) + amount > STAT_MAX:
            raise AssetError(f"{asset.name} can raise {stat} only to {STAT_MAX}")
    for stat, amount in lowered.items():
        if character.stats.value(stat) < amount:
            raise AssetError(f"{stat} is already 0")


def _apply_marking(character: Character, asset_id: str, ability: int, changes: StatChanges) -> None:
    """Make the one-time changes marking an ability calls for."""
    for stat, amount in changes.items():
        setattr(character.stats, stat, character.stats.value(stat) + amount)
    if (asset_id, ability) == ("battle_scarred", 2):
        character.health = min(character.health, character.health_max)
    character.momentum = min(character.momentum, character.bounds.max)


def change_asset_meter(
    character: Character, data: Datasworn, asset_id: str, meter: str, amount: int
) -> int:
    """Add to or take from an asset's meter, within 0 and its maximum.

    Returns:
        The change actually made.

    Raises:
        AssetError: If the character doesn't own the asset or it has no such meter.
    """
    target = owned(character, asset_id)
    if meter not in target.meters:
        raise AssetError(f"{data.asset(asset_id).name} has no meter {meter!r}")
    before = target.meters[meter]
    after = max(0, min(meter_max(data, target, meter), before + amount))
    target.meters[meter] = after
    character.momentum = min(character.momentum, character.bounds.max)
    return after - before


def set_field(character: Character, data: Datasworn, asset_id: str, field: str, value: str) -> None:
    """Fill in an asset's text or select field, such as a companion's name.

    Choosing Ironclad's geared for war marks encumbered, and choosing lightly armored clears
    it, as the asset says.

    Raises:
        AssetError: If the character doesn't own the asset, it has no such field, or the value
            isn't one of a select field's choices.
    """
    target = owned(character, asset_id)
    asset = data.asset(asset_id)
    if field in asset.selects:
        choices = asset.selects[field].choices
        if value not in choices:
            raise AssetError(f"{asset.name}'s {field} must be one of: {', '.join(choices)}")
    elif field not in asset.texts:
        fields = [*asset.texts, *asset.selects]
        raise AssetError(
            f"{asset.name} has no field {field!r}; it has: {', '.join(fields) or 'none'}"
        )
    before = target.fields.get(field)
    target.fields[field] = value
    if (asset_id, field) == ("ironclad", "equipped"):
        if value == "geared_for_war":
            character.mark_debility("encumbered")
        elif before == "geared_for_war":
            character.clear_debility("encumbered")


def discard(character: Character, asset_id: str) -> None:
    """Remove an owned asset, as Oathbreaker's redemption or a companion's death does.

    Raises:
        AssetError: If the character doesn't own it.
    """
    character.assets.remove(owned(character, asset_id))
    character.health = min(character.health, character.health_max)
    character.momentum = min(character.momentum, character.bounds.max)


def set_debility(character: Character, asset_id: str, *, on: bool) -> None:
    """Make an asset count as a debility, or stop it counting.

    Fated counts as one once its protection is used, and Leech while its rune is unquenched.

    Raises:
        AssetError: If the character doesn't own it.
    """
    owned(character, asset_id).debility = on
    character.momentum = min(character.momentum, character.bounds.max)
