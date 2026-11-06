"""Campaign setup: what the character creation walkthrough asks, and the campaign it starts.

The walkthrough follows the rulebook's campaign setup (page 202): create the character,
create the world, mark background bonds, write the background vow, envision the inciting
incident, set the scene, and swear an iron vow. [`Setup`][ironsworn_tui.creation.Setup]
holds the answers, [`begin_campaign`][ironsworn_tui.creation.begin_campaign] turns them
into a campaign, and [`open_play`][ironsworn_tui.creation.open_play] makes the first move.
"""

import random
from dataclasses import dataclass, field
from typing import Literal

from ironsworn_tui.assets import set_field
from ironsworn_tui.campaign import (
    STAT_CHANGE_ABILITIES,
    Campaign,
    World,
    WorldTruth,
    create_character,
    new_campaign,
)
from ironsworn_tui.rules.datasworn import Datasworn, Stat, plain_text
from ironsworn_tui.rules.oracles import roll_oracle
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, TurnEngine

type Start = Literal["in_media_res", "prologue"]

NAME_TABLES = ("classic/name/ironlander/a", "classic/name/ironlander/b")
PLACE_PREFIX = "classic/settlement/quick_name/prefix"
PLACE_SUFFIX = "classic/settlement/quick_name/suffix"
SPARK_TABLES = ("classic/action_and_theme/action", "classic/action_and_theme/theme")


@dataclass
class AssetPick:
    """A starting asset, as the walkthrough picks it.

    Attributes:
        id: The asset id, such as `hawk`.
        ability: The ability to mark, from 1 to 3, for an asset that starts with none
            marked, such as a companion. None for an asset that starts with one.
        fields: Its text and select fields, such as a companion's name. A select field holds
            the choice id.
    """

    id: str
    ability: int | None = None
    fields: dict[str, str] = field(default_factory=dict[str, str])

    @property
    def spec(self) -> str:
        """The asset as `create_character` takes it, such as `hawk:1`."""
        return f"{self.id}:{self.ability}" if self.ability is not None else self.id


@dataclass
class Setup:
    """Everything the walkthrough asks before play.

    Attributes:
        name: The character's name.
        description: A few words about them, such as "the Destructor".
        stats: The five stats, given 3, 2, 2, 1, and 1.
        assets: The three starting assets.
        harm: 2 with a deadly weapon, 1 without.
        truths: The world truths the player chose: the option's index by truth id. A truth
            left open isn't here.
        region: The id of the region where the story begins, or None.
        place: The place where the story begins.
        bonds: Up to three people or communities the character shares a bond with.
        background_vow: The background vow's name.
        background_rank: Its rank, extreme or epic.
        inciting_incident: The problem that drives the character into action.
        start: `in_media_res` to begin as the inciting incident happens and swear the vow at
            once, or
            `prologue` to start in the normal world.
        scene: The opening scene, which becomes the situation line.
        vow: The vow to swear in media res. Unused in a prologue.
        vow_rank: Its rank, troublesome, dangerous, or formidable.
    """

    name: str
    description: str
    stats: dict[Stat, int]
    assets: list[AssetPick]
    harm: int = 2
    truths: dict[str, int] = field(default_factory=dict[str, int])
    region: str | None = None
    place: str = ""
    bonds: list[str] = field(default_factory=list[str])
    background_vow: str = ""
    background_rank: Rank = Rank.EPIC
    inciting_incident: str = ""
    start: Start = "in_media_res"
    scene: str = ""
    vow: str = ""
    vow_rank: Rank = Rank.DANGEROUS


def begin_campaign(data: Datasworn, setup: Setup) -> Campaign:
    """Create the character and the campaign from the walkthrough's answers.

    Args:
        data: The Datasworn data.
        setup: The answers.

    Returns:
        The campaign, with the world, the inciting incident, and the scene in the log.

    Raises:
        ValueError: If the stats, assets, bonds, or background vow aren't valid.
        AssetError: If an asset's ability pick or a field isn't valid.
        UnknownIdError: If an asset id isn't in the data.
    """
    character = create_character(
        data,
        setup.name,
        setup.description,
        setup.stats,
        [pick.spec for pick in setup.assets],
        harm=setup.harm,
    )
    for pick in setup.assets:
        for name, value in pick.fields.items():
            if value:
                set_field(character, data, pick.id, name, value)
    campaign = new_campaign(character, setup.background_vow, setup.background_rank, setup.bonds)
    campaign.world = World(
        truths=[
            WorldTruth(name=truth.name, text=truth.options[setup.truths[truth_id]].description)
            for truth_id, truth in data.truths.items()
            if truth_id in setup.truths
        ],
        region=data.regions[setup.region].name if setup.region is not None else None,
        place=setup.place,
        inciting_incident=setup.inciting_incident,
    )
    if setup.inciting_incident:
        campaign.add_log("player_note", f"Inciting incident: {setup.inciting_incident}")
    if setup.scene:
        campaign.situation = setup.scene
        campaign.add_log("command", f"Scene: {setup.scene}")
    return campaign


def open_play(engine: TurnEngine, setup: Setup) -> None:
    """Start play: swear the vow in media res, or note how to swear it after a prologue.

    The engine saves the campaign either way, with the Swear an Iron Vow card waiting in
    media res.

    Args:
        engine: The engine for the campaign `begin_campaign` made.
        setup: The answers.
    """
    if setup.start == "in_media_res" and setup.vow:
        engine.make_move("swear_an_iron_vow", inputs=MoveInputs(vow=setup.vow, rank=setup.vow_rank))
        engine.save()
        return
    engine.campaign.add_log(
        "note",
        "When your inciting incident comes, Swear an Iron Vow with /vow swear, such as /vow "
        "swear dangerous Find my brother.",
    )
    engine.save()


def needs_ability(data: Datasworn, asset_id: str) -> bool:
    """True when an asset doesn't have a starting ability, as a companion doesn't."""
    return not any(ability.enabled for ability in data.asset(asset_id).abilities)


def pickable_abilities(data: Datasworn, asset_id: str) -> tuple[int, ...]:
    """The abilities, from 1 to 3, a new character can mark on an asset that starts with none.

    Shadow-Kin's and Battle-Scarred's first abilities change stats, so they're bought in play.
    """
    return tuple(
        number
        for number in range(1, len(data.asset(asset_id).abilities) + 1)
        if (asset_id, number) not in STAT_CHANGE_ABILITIES
    )


def roll_truth(data: Datasworn, truth_id: str, rng: random.Random) -> tuple[int, int]:
    """Roll 1 to 100 for a world truth.

    Returns:
        The roll and the index of the option it picks.
    """
    roll = rng.randint(1, 100)
    return roll, data.truths[truth_id].option_for(roll)


def roll_name(data: Datasworn, rng: random.Random) -> str:
    """Roll an Ironlander name, on one of the two name tables, as the rulebook says."""
    table = NAME_TABLES[rng.randint(1, len(NAME_TABLES)) - 1]
    return plain_text(roll_oracle(data, table, rng).text)


def roll_place_name(data: Datasworn, rng: random.Random) -> str:
    """Roll a settlement's name from the quick name tables, such as Ravenford."""
    prefix = plain_text(roll_oracle(data, PLACE_PREFIX, rng).text)
    suffix = plain_text(roll_oracle(data, PLACE_SUFFIX, rng).text)
    return prefix + suffix


def roll_spark(data: Datasworn, rng: random.Random) -> str:
    """Roll the action and theme oracles for an idea, such as "Clash and Ally"."""
    action, theme = (plain_text(roll_oracle(data, table, rng).text) for table in SPARK_TABLES)
    return f"{action} and {theme}"


def quest_starters(data: Datasworn, setup: Setup) -> list[tuple[str, str]]:
    """The quest starters of the chosen truths and region, as (source, text) pairs."""
    starters = [
        (truth.name, truth.options[setup.truths[truth_id]].quest_starter)
        for truth_id, truth in data.truths.items()
        if truth_id in setup.truths
    ]
    if setup.region is not None:
        region = data.regions[setup.region]
        starters.append((region.name, region.quest_starter))
    return starters
