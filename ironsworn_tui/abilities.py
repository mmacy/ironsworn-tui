"""What each asset ability does to a roll, written by hand from the ability text.

Datasworn says which moves an ability enhances and which stat or meter it lets a move roll,
but the bonuses themselves are prose. Each ability gets an entry here: either the boosts the
player can turn on when making a move, or a reminder saying why the app doesn't apply it.

The player turns a boost on when its condition holds in the fiction, such as "by hunting".
The app never turns one on by itself, because it can't judge the fiction.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from ironsworn_tui.outcomes import (
    AddLasting,
    AddToNextMove,
    AssetDebility,
    AssetMeterChange,
    AssetMeterFromRank,
    Choose,
    DiscardAsset,
    Effect,
    ExperiencePerAbility,
    FollowUp,
    GainExperience,
    InflictHarm,
    InflictRolledHarm,
    MarkDebility,
    MarkExperience,
    MarkProgress,
    MaskTrack,
    MaxSpirit,
    MeterChange,
    Momentum,
    MomentumFromMeter,
    Note,
    Option,
    RaiseStat,
    SetInitiative,
)
from ironsworn_tui.rules.datasworn import Stat
from ironsworn_tui.rules.dice import Hit

type RollKind = Literal["stat", "meter", "field", "condition"]


@dataclass(frozen=True)
class RollWith:
    """What a boost lets a move roll instead of its usual stat.

    Attributes:
        kind: `stat` for a stat, `meter` for the asset's own meter (a warband's strength),
            `field` for the stat an asset's select field names (a Devotant's god's stat), or
            `condition` for a condition meter (spirit).
        name: The stat, meter, field, or condition meter.
    """

    kind: RollKind
    name: str


def stat(name: Stat) -> RollWith:
    """Roll a stat instead."""
    return RollWith("stat", name)


def meter(name: str) -> RollWith:
    """Roll the asset's own meter instead."""
    return RollWith("meter", name)


type Reroll = Literal["any", "miss", "weak_or_miss", "one_challenge_on_miss"]
"""When a boost allows a reroll: after any result, or only after the results named."""

type Limit = Literal["fight", "one_time"]


@dataclass(frozen=True)
class Boost:
    """One way an ability changes a move, which the player turns on before rolling.

    Attributes:
        label: A short name for the boost, shown after the asset's name.
        moves: The move ids it applies to, or None for any move whose condition holds.
        add: The add.
        add_meter: An asset meter whose value is added, as Fortune Hunter's wealth is. It's
            read before `before` applies, as is a meter the boost rolls.
        roll: What the move rolls instead of its usual stat.
        momentum_on_hit: Momentum on a strong or weak hit.
        momentum_on_strong: Momentum on a strong hit.
        harm: Extra harm on a hit.
        harm_on_strong: Extra harm on a strong hit.
        set_harm: The harm a hit inflicts instead of the character's usual harm.
        burn_harm: Extra harm when the player burns momentum on the roll.
        reroll: When the player may reroll any of the dice, once.
        reroll_add: An add for the reroll, as Empowered's "roll all dice again and add +1".
        weak_as_miss: A weak hit counts as a miss.
        strong_as_weak: A strong hit counts as a weak hit.
        automatic: The move is an automatic strong hit, with no roll.
        skip: The move isn't made at all, as when a Shield-Bearer sacrifices the shield.
        before: Effects applied before rolling, such as a cost.
        after: Effects applied after the result, whatever it is.
        on_hit: Effects on a strong or weak hit.
        on_strong: Effects on a strong hit.
        on_weak: Effects on a weak hit.
        on_miss: Effects on a miss.
        on_strong_match: Effects on a strong hit with a match.
        on_burn: Effects when the player burns momentum, applied after the reset.
        rerolled_miss: Effects when the result is still a miss after the reroll.
        on_one: Effects when the action die is a 1.
        late_add: An add the player may take after rolling, paying `late_cost`.
        late_cost: What the late add costs.
        experience: Extra experience when Fulfill Your Vow marks experience.
        extra_choices: More options to choose on a hit, as Wildblood's camp gives.
        on_option: Effects added to an outcome option, by the start of its label, such as
            `Relax`.
        limit: `fight` for once per fight, or `one_time` for once ever.
        tide: True when the boost needs Turn the Tide armed.
        field: An asset field and the choice it must hold, such as Ironclad's armor.
        stat_field: A select field whose stat the move must roll, as a Masked mask's.
        only_stat: A stat the move must roll, as an elixir's or a pelt's.
        rolled: A stat the roll must use for the boost to apply, as "Endure Stress +heart".
        needs: Other abilities of the same asset, from 1 to 3, that must be marked.
        unleash: An asset meter the player spends an amount of, as Lightbearer's light.
        burn_initiative: Take initiative when burning improves a miss to a weak hit, once
            per fight.
        burn_progress: Allows burning momentum on a progress roll to cancel one challenge
            die.
    """

    label: str
    moves: tuple[str, ...] | None
    add: int = 0
    add_meter: str | None = None
    roll: RollWith | None = None
    momentum_on_hit: int = 0
    momentum_on_strong: int = 0
    harm: int = 0
    harm_on_strong: int = 0
    set_harm: int | None = None
    burn_harm: int = 0
    reroll: Reroll | None = None
    reroll_add: int = 0
    weak_as_miss: bool = False
    strong_as_weak: bool = False
    automatic: bool = False
    skip: bool = False
    before: tuple[Effect, ...] = ()
    after: tuple[Effect, ...] = ()
    on_hit: tuple[Effect, ...] = ()
    on_strong: tuple[Effect, ...] = ()
    on_weak: tuple[Effect, ...] = ()
    on_miss: tuple[Effect, ...] = ()
    on_strong_match: tuple[Effect, ...] = ()
    on_burn: tuple[Effect, ...] = ()
    rerolled_miss: tuple[Effect, ...] = ()
    on_one: tuple[Effect, ...] = ()
    late_add: int = 0
    late_cost: tuple[Effect, ...] = ()
    experience: int = 0
    extra_choices: int = 0
    on_option: tuple[tuple[str, tuple[Effect, ...]], ...] = ()
    limit: Limit | None = None
    tide: bool = False
    field: tuple[str, str] | None = None
    stat_field: str | None = None
    only_stat: Stat | None = None
    rolled: Stat | None = None
    needs: tuple[int, ...] = ()
    unleash: str | None = None
    burn_initiative: bool = False
    burn_progress: bool = False


@dataclass(frozen=True)
class Reminder:
    """An ability the app doesn't apply on a roll, and why.

    Attributes:
        why: What the ability does instead, such as a one-time change applied when it's
            marked, or an effect on an ally.
    """

    why: str


@dataclass(frozen=True)
class AssetMove:
    """An ability that adds a move, such as a ritual's. The move's outcomes apply it.

    Attributes:
        move: The move id.
        boosts: Boosts the ability also gives, as Invoke's rolls with essence do.
    """

    move: str
    boosts: tuple[Boost, ...] = ()


type Entry = tuple[Boost, ...] | Reminder | AssetMove


# Moves
FD = "face_danger"
SAA = "secure_an_advantage"
GI = "gather_information"
HEAL = "heal"
RESUPPLY = "resupply"
CAMP = "make_camp"
JOURNEY = "undertake_a_journey"
ARRIVE = "reach_your_destination"
COMPEL = "compel"
SOJOURN = "sojourn"
CIRCLE = "draw_the_circle"
BOND = "forge_a_bond"
TEST_BOND = "test_your_bond"
FRAY = "enter_the_fray"
STRIKE = "strike"
CLASH = "clash"
BATTLE = "battle"
END_FIGHT = "end_the_fight"
HARM = "endure_harm"
STRESS = "endure_stress"
DEATH = "face_death"
DESOLATION = "face_desolation"
COMPANION_HARM = "companion_endure_harm"
SWEAR = "swear_an_iron_vow"
FULFILL = "fulfill_your_vow"
ATTACKS = (STRIKE, CLASH)
RITUALS = (
    "augur",
    "awaken_simulacrum",
    "bind",
    "commune",
    "cast_runes",
    "invoke",
    "keen",
    "draw_blood_rune",
    "capture_light",
    "scry",
    "shadow_walk",
    "sway",
    "fashion_talisman",
    "tether",
    "focus_totem",
    "paint_visage",
    "ward",
)

SUPPLY_COST = (MeterChange("supply", -1),)
MOMENTUM_COST = (Momentum(-1),)


def _either(first: tuple[str, Effect], second: tuple[str, Effect]) -> Choose:
    return Choose((Option(first[0], (first[1],)), Option(second[0], (second[1],))))


def _maybe(label: str, *effects: Effect) -> Choose:
    return Choose((Option(label, effects),), minimum=0)


SUPPLY_OR_MOMENTUM = _either(("+1 supply", MeterChange("supply", 1)), ("+1 momentum", Momentum(1)))
SPIRIT_OR_MOMENTUM = _either(("+1 spirit", MeterChange("spirit", 1)), ("+1 momentum", Momentum(1)))
MOMENTUM_OR_SPIRIT = _either(("+1 momentum", Momentum(1)), ("+1 spirit", MeterChange("spirit", 1)))


def _ritual(asset: str, move: str) -> tuple[Boost, ...]:
    """Every ritual's third ability: "When you perform this ritual, add +1 and take +1
    momentum on a hit." Invoke's takes +1 essence instead."""
    if asset == "invoke":
        return (
            Boost(
                "Perform this ritual",
                (move,),
                add=1,
                on_hit=(AssetMeterChange(asset, "essence", 1),),
            ),
        )
    return (Boost("Perform this ritual", (move,), add=1, momentum_on_hit=1),)


UPGRADES_RESULT = "Changes the result of the asset's move, which the outcomes table applies."

ABILITIES: dict[tuple[str, int], Entry] = {
    # Combat talents
    ("archer", 1): (
        Boost("Trust your instincts", (SAA,), add=1, roll=stat("wits"), momentum_on_strong=2),
        Boost("Line up your shot", (SAA,), add=1, roll=stat("edge"), momentum_on_hit=1),
    ),
    ("archer", 2): (
        Boost(
            "Extra shots",
            ATTACKS,
            before=SUPPLY_COST,
            reroll="any",
            harm=2,
            momentum_on_hit=1,
            limit="fight",
        ),
    ),
    ("archer", 3): (Boost("Hunting", (RESUPPLY,), add=1, momentum_on_hit=1),),
    ("berserker", 1): (Boost("Wild nature", (SAA, COMPEL), add=1, momentum_on_hit=1),),
    ("berserker", 2): (
        Boost("Rage: push yourself", ATTACKS, harm=1, after=(FollowUp(HARM, 1),)),
        Boost("Rage: lose yourself", ATTACKS, harm=1, after=(FollowUp(STRESS, 1),)),
    ),
    ("berserker", 3): (
        Boost(
            "Inflame your wildness",
            (HARM,),
            weak_as_miss=True,
            on_strong=(_maybe("Embrace the pain", MomentumFromMeter("health")),),
        ),
    ),
    ("brawler", 1): (
        Boost(
            "Brawling",
            (SAA,),
            add=1,
            roll=stat("iron"),
            on_hit=(_maybe("Inflict 1 harm", InflictHarm(1)),),
        ),
    ),
    ("brawler", 2): (
        Boost(
            "Deadly intent",
            (STRIKE,),
            add=2,
            set_harm=2,
            on_weak=MOMENTUM_COST,
            on_miss=MOMENTUM_COST,
        ),
    ),
    ("brawler", 3): (Boost("Against a brawling attack", (FD, CLASH), add=1, momentum_on_hit=1),),
    ("cutthroat", 1): (
        Boost("Unsuspecting foe: +2", (STRIKE,), add=2, momentum_on_hit=1),
        Boost("Unsuspecting foe: +2 harm", (STRIKE,), harm=2),
    ),
    ("cutthroat", 2): (Boost("Your blade", (COMPEL, FD), add=1),),
    ("cutthroat", 3): (
        Boost("Feint", (SAA,), roll=stat("shadow"), reroll="any", momentum_on_hit=1, limit="fight"),
    ),
    ("duelist", 1): (Boost("Two blades", ATTACKS, add=2, harm_on_strong=1, weak_as_miss=True),),
    ("duelist", 2): (
        Boost("Bold display", (SAA,), roll=stat("edge"), reroll="any", limit="fight"),
    ),
    ("duelist", 3): (
        Boost("Add +2", (CIRCLE,), add=2),
        Boost("Take +2 momentum", (CIRCLE,), momentum_on_hit=2),
    ),
    ("fletcher", 1): (Boost("Fine arrows", (SAA,), add=1, on_hit=(SUPPLY_OR_MOMENTUM,)),),
    ("fletcher", 2): (Boost("Recover arrows", (RESUPPLY,), add=2),),
    ("fletcher", 3): AssetMove("craft_arrow"),
    ("ironclad", 1): (
        Boost(
            "Lightly armored",
            (HARM,),
            add=1,
            momentum_on_hit=1,
            field=("equipped", "lightly_armored"),
        ),
        Boost(
            "Geared for war",
            (HARM,),
            add=2,
            momentum_on_hit=1,
            field=("equipped", "geared_for_war"),
        ),
    ),
    ("ironclad", 2): (
        Boost("Geared for war", (CLASH,), add=1, field=("equipped", "geared_for_war")),
    ),
    ("ironclad", 3): (Boost("Strength of arms", (COMPEL,), add=2),),
    ("long_arm", 1): (
        Boost(
            "Staff as a simple weapon",
            ATTACKS,
            add=1,
            roll=stat("edge"),
            set_harm=1,
            momentum_on_hit=1,
        ),
    ),
    ("long_arm", 2): (
        Boost("Disarm, trip, shove, or stun", (SAA,), add=1, roll=stat("edge"), momentum_on_hit=1),
    ),
    ("long_arm", 3): (Boost("Your staff's support", (JOURNEY,), momentum_on_strong=1),),
    ("shield_bearer", 1): (
        Boost("Shield as cover", (FD,), add=1),
        Boost("Close quarters", (CLASH,), momentum_on_strong=1),
    ),
    ("shield_bearer", 2): (Boost("Painted shield", (STRESS,), add=1, momentum_on_hit=1),),
    ("shield_bearer", 3): (
        Boost(
            "Sacrifice your shield",
            (HARM,),
            skip=True,
            # The card limits only the initiative to once per fight, and the shield is
            # destroyed, so the app doesn't limit the sacrifice.
            after=(SetInitiative("character"), Note("Your shield is destroyed.")),
        ),
    ),
    ("skirmisher", 1): (
        Boost(
            "Hold them at bay: iron",
            (FD,),
            roll=stat("iron"),
            on_hit=(
                AddToNextMove(1),
                Note("Strike (if you have initiative) or Clash now, and add +1."),
            ),
        ),
        Boost("Hold them at bay: edge", (FD,), roll=stat("edge"), momentum_on_hit=1),
    ),
    ("skirmisher", 2): (
        Boost(
            "Drive your spear home",
            (STRIKE,),
            add=1,
            harm=2,
            on_hit=(Note("If the fight continues, Face Danger +iron to recover your spear."),),
        ),
    ),
    ("skirmisher", 3): (Boost("Brace against a charge", (SAA,), add=1, momentum_on_hit=1),),
    ("slinger", 1): (Boost("Barrage", (FRAY,), on_strong=(InflictHarm(),)),),
    ("slinger", 2): (
        Boost("Hold them back", (STRIKE,), set_harm=1, on_weak=(SetInitiative("character"),)),
        Boost("Hit them hard", (STRIKE,), harm=1, on_hit=MOMENTUM_COST),
    ),
    ("slinger", 3): (Boost("Special stones", (SAA,), add=1, on_hit=(SUPPLY_OR_MOMENTUM,)),),
    ("sunderer", 1): (Boost("Your axe", ATTACKS, before=MOMENTUM_COST, harm=1),),
    ("sunderer", 2): (Boost("Promise of violence", (COMPEL, SAA), add=1, momentum_on_hit=1),),
    ("sunderer", 3): AssetMove("carve_rune"),
    ("swordmaster", 1): (
        Boost(
            "Your sword",
            ATTACKS,
            burn_harm=2,
            on_burn=(AddToNextMove(1), Note("The +1 is for your next move if the fight goes on.")),
        ),
    ),
    ("swordmaster", 2): (
        Boost(
            "Follow with a Strike",
            (CLASH,),
            on_strong=(AddToNextMove(1), Note("The +1 is for a Strike right after this.")),
        ),
    ),
    ("swordmaster", 3): (
        Boost("Kneel and grasp your sword", (SWEAR,), add=1, momentum_on_hit=1),
        Boost(
            "Let the edge draw blood",
            (SWEAR,),
            add=1,
            momentum_on_hit=2,
            after=(FollowUp(HARM, 1),),
        ),
    ),
    ("thunder_bringer", 1): (
        Boost("Hit or break an object", (FD, SAA, COMPEL), add=1, momentum_on_hit=1),
    ),
    ("thunder_bringer", 2): (
        Boost(
            "Knock back or stun",
            (STRIKE,),
            set_harm=1,
            momentum_on_hit=2,
            on_strong=(AddToNextMove(1),),
        ),
    ),
    ("thunder_bringer", 3): (
        Boost(
            "All your fury",
            (STRIKE,),
            tide=True,
            reroll="any",
            harm_on_strong=2,
            weak_as_miss=True,
        ),
    ),
    # Companions
    ("cave_lion", 1): (
        Boost(
            "Chase down big game", (RESUPPLY,), roll=stat("edge"), on_strong=(SUPPLY_OR_MOMENTUM,)
        ),
    ),
    ("cave_lion", 2): (
        Boost("Send your cat", (FRAY, STRIKE), roll=stat("edge"), momentum_on_hit=2),
    ),
    ("cave_lion", 3): (
        Boost(
            "Alert to trouble",
            (CAMP,),
            on_option=(("Relax", (MeterChange("spirit", 1),)), ("Focus", (Momentum(1),))),
        ),
    ),
    ("giant_spider", 1): (Boost("Your spider scouts", (SAA,), add=1, momentum_on_hit=1),),
    ("giant_spider", 2): (
        Boost(
            "Your spider studies someone",
            (FD,),
            roll=stat("shadow"),
            on_hit=(AddLasting("spider_reflection"),),
        ),
    ),
    ("giant_spider", 3): (
        Boost(
            "Your spider's trap", (FRAY,), add=1, roll=stat("shadow"), on_strong=(InflictHarm(2),)
        ),
    ),
    ("hawk", 1): (
        Boost("Your hawk aloft", (JOURNEY,), add=1),
        Boost("Hunting small game", (RESUPPLY,), add=1),
    ),
    ("hawk", 2): (
        Boost("Harass and distract", (SAA,), add=1, roll=stat("edge"), momentum_on_hit=1),
    ),
    ("hawk", 3): (
        Boost("Detect a threat", (FD,), add=2, roll=stat("wits")),
        Boost("Against an ambush", (FRAY,), add=2, roll=stat("wits")),
    ),
    ("horse", 1): (
        Boost("Speed and grace", (FD,), add=1, roll=stat("edge")),
        Boost("Ride", (JOURNEY,), add=1),
    ),
    ("horse", 2): (
        Boost("Charge into the fray", (FRAY,), add=1, roll=stat("heart"), momentum_on_hit=1),
        Boost("Charge", (SAA,), add=1, roll=stat("heart"), momentum_on_hit=1),
    ),
    ("horse", 3): (Boost("Mounted", ATTACKS, add=1, harm=1),),
    ("hound", 1): (Boost("Keen senses", (GI,), add=1, momentum_on_hit=1),),
    ("hound", 2): (
        Boost(
            "Alongside your hound",
            ATTACKS,
            on_hit=(_either(("+1 harm", InflictHarm(1)), ("+1 momentum", Momentum(1))),),
        ),
    ),
    ("hound", 3): (Boost("In your hound's company", (STRESS,), add=1),),
    ("kindred", 1): (Boost("Your companion's expertise", None, add=1),),
    ("kindred", 2): (
        Boost("Alongside your companion", (CLASH, BATTLE), add=1),
        Boost("Standing together", (FD,), add=1),
    ),
    ("kindred", 3): (Boost("In their presence", (DESOLATION,), add=1),),
    ("mammoth", 1): (
        Boost("Your mammoth travels with you", (JOURNEY,), add=2, before=MOMENTUM_COST),
    ),
    ("mammoth", 2): (Boost("Your mammoth's health", (CAMP,), roll=meter("health")),),
    ("mammoth", 3): (Boost("Ride against a pack", ATTACKS, add=1, harm=1),),
    ("owl", 1): (
        Boost("Your owl hunts at night", (RESUPPLY,), momentum_on_hit=2),
        Boost("Ambush in darkness", (FRAY,), add=1, roll=stat("wits"), momentum_on_hit=1),
    ),
    ("owl", 2): (
        Boost("Your owl's knowledge: +1", RITUALS, add=1),
        Boost("Your owl's knowledge: +1 momentum", RITUALS, momentum_on_hit=1),
    ),
    ("owl", 3): (
        Boost("Your owl's health", (DEATH,), before=(MomentumFromMeter("health", "owl"),)),
    ),
    ("raven", 1): (
        Boost("Your raven's trickery", (SAA,), add=1, roll=stat("shadow"), momentum_on_hit=1),
        Boost("Your raven's trickery", (FD,), add=1, roll=stat("shadow"), momentum_on_hit=1),
    ),
    ("raven", 2): (Boost("Your raven", (DEATH,), add=2, momentum_on_hit=1),),
    ("raven", 3): Reminder("Lets you make some moves from a distance; there's nothing to roll."),
    ("young_wyvern", 1): (
        Boost(
            "Your wyvern on the journey",
            (JOURNEY,),
            on_hit=(_maybe("-1 supply for +2 momentum", MeterChange("supply", -1), Momentum(2)),),
        ),
    ),
    ("young_wyvern", 2): (Boost("Your wyvern", (COMPANION_HARM,), add=2, momentum_on_hit=1),),
    ("young_wyvern", 3): (Boost("Command your wyvern", (STRIKE,), roll=stat("heart"), set_harm=3),),
    # Paths
    ("alchemist", 1): AssetMove("create_elixir"),
    ("alchemist", 2): Reminder(UPGRADES_RESULT),
    ("alchemist", 3): (Boost("Prepare an elixir", ("create_elixir",), add=1, momentum_on_hit=1),),
    ("animal_kin", 1): (Boost("An animal", None, add=1, momentum_on_hit=1),),
    ("animal_kin", 2): (
        Boost(
            "Bond with your companion",
            (BOND,),
            automatic=True,
            on_strong=(MarkProgress("bonds"), GainExperience(1)),
        ),
    ),
    ("animal_kin", 3): (
        Boost("Leverage your companion", None, reroll="any", momentum_on_hit=1, limit="fight"),
    ),
    ("banner_sworn", 1): (
        Boost("Serve your leader", (SWEAR,), reroll="any"),
        Boost("Served your leader", (FULFILL,), experience=1),
    ),
    ("banner_sworn", 2): (
        Boost("With your banner-kin", (SOJOURN, CAMP), add=1, momentum_on_hit=1),
    ),
    ("banner_sworn", 3): (
        Boost("Bearing your banner", (FRAY,), add=1, momentum_on_hit=1),
        Boost("Carrying your banner", None, on_burn=(Momentum(1),)),
    ),
    ("battle_scarred", 1): Reminder("Moves stat points once, when it's marked."),
    ("battle_scarred", 2): (
        Boost("Endure Stress +heart", (STRESS,), momentum_on_strong=1, rolled="heart"),
    ),
    ("battle_scarred", 3): (
        Boost("Stared down death: wits", (HARM,), roll=stat("wits"), momentum_on_hit=1),
        Boost("Stared down death: heart", (HARM,), roll=stat("heart"), momentum_on_hit=1),
    ),
    ("blade_bound", 1): (Boost("Your kin-blade", (FRAY, CIRCLE), add=1, momentum_on_hit=1),),
    ("blade_bound", 2): (
        Boost(
            "Whispers of your kin-blade",
            (GI,),
            add=1,
            momentum_on_hit=2,
            after=(FollowUp(STRESS, 2),),
        ),
    ),
    ("blade_bound", 3): (
        Boost("Savage harm", (STRIKE,), add=1, harm=2, after=(FollowUp(STRESS, 2),)),
    ),
    ("bonded", 1): (Boost("An add for a bond", None, add=1),),
    ("bonded", 2): Reminder("Applies when a bonds box fills: the turn engine adds the effects."),
    ("bonded", 3): (
        Boost(
            "Cling to your bond-kin",
            None,
            reroll="miss",
            rerolled_miss=(
                Choose(
                    (
                        Option("Mark shaken", (MarkDebility("shaken"),)),
                        Option("Mark corrupted", (MarkDebility("corrupted"),)),
                        Option("Both are marked: Face Desolation", (FollowUp(DESOLATION),)),
                    )
                ),
            ),
        ),
    ),
    ("commander", 1): (
        Boost("Command your warband", (FD, SAA, COMPEL, BATTLE), roll=meter("strength")),
        Boost(
            "Your warband rests",
            (CAMP, SOJOURN),
            on_hit=(AssetMeterChange("commander", "strength", 1),),
        ),
    ),
    ("commander", 2): (Boost("Dispatch scouts", (GI, RESUPPLY), roll=meter("strength")),),
    ("commander", 3): (
        Boost("Your bonded warband", (FD, SAA, COMPEL, BATTLE, GI, RESUPPLY), momentum_on_hit=1),
    ),
    ("dancer", 1): (
        Boost(
            "Dance for an audience",
            (SAA,),
            add=1,
            roll=stat("edge"),
            momentum_on_hit=2,
            on_strong=(AddLasting("audience"),),
        ),
    ),
    ("dancer", 2): (
        Boost("Nimbly avoid attacks", (FD,), add=1, roll=stat("edge"), momentum_on_hit=1),
    ),
    ("dancer", 3): AssetMove("commemorate"),
    ("devotant", 1): (
        Boost("Ask for a blessing", (SAA,), roll=RollWith("field", "stat"), momentum_on_hit=2),
    ),
    ("devotant", 2): (
        Boost("A divine quest", (SWEAR,), roll=RollWith("field", "stat"), reroll="any"),
        Boost("Served your god", (FULFILL,), experience=1),
    ),
    ("devotant", 3): (
        Boost("Share the word", (SOJOURN,), roll=RollWith("field", "stat"), momentum_on_hit=1),
    ),
    ("empowered", 1): (
        Boost(
            "Rights of hospitality",
            (SOJOURN,),
            reroll="weak_or_miss",
            reroll_add=1,
            rerolled_miss=(Note("You are refused, and your presumption causes new trouble."),),
        ),
    ),
    ("empowered", 2): (Boost("Exert your title", (COMPEL,), add=1, momentum_on_hit=1),),
    ("empowered", 3): (
        Boost(
            "As an equal, or for one of lower station",
            (BOND, SWEAR),
            add=1,
            on_hit=(MOMENTUM_OR_SPIRIT,),
        ),
    ),
    ("fated", 1): (
        Boost(
            "Not yet your time",
            (DEATH, DESOLATION),
            automatic=True,
            after=(AssetDebility("fated", on=True),),
        ),
    ),
    ("fated", 2): Reminder(
        "Applies when you Reach a Milestone on your background vow: take +2 momentum or +1 "
        "spirit with /adjust."
    ),
    ("fated", 3): (Boost("Your fate is at hand", (FULFILL,), reroll="any"),),
    ("fortune_hunter", 1): (
        Boost("Promise of payment", (SWEAR,), add=1),
        Boost("Paid", (FULFILL,), on_hit=(AssetMeterFromRank("fortune_hunter", "wealth"),)),
        Boost(
            "Leverage wealth",
            None,
            add_meter="wealth",
            before=(AssetMeterChange("fortune_hunter", "wealth", -1),),
        ),
    ),
    ("fortune_hunter", 2): Reminder(
        "Trade wealth for supply with /asset meter fortune_hunter wealth -1 and /adjust supply 2."
    ),
    ("fortune_hunter", 3): (
        Boost(
            "Find an object of value",
            (RESUPPLY,),
            on_strong_match=(
                _maybe(
                    "+1 wealth instead of 1 supply",
                    MeterChange("supply", -1),
                    AssetMeterChange("fortune_hunter", "wealth", 1),
                ),
            ),
        ),
    ),
    ("herbalist", 1): (
        Boost("Herbal remedies: +2", (HEAL,), add=2),
        Boost("Herbal remedies: +1 health", (HEAL,), on_hit=(MeterChange("health", 1),)),
    ),
    ("herbalist", 2): (Boost("Heal another", (HEAL,), on_hit=(SPIRIT_OR_MOMENTUM,)),),
    ("herbalist", 3): (
        Boost("Restorative meal", (CAMP,), on_option=(("Partake", (MeterChange("health", 1),)),)),
    ),
    ("honorbound", 1): (
        Boost("Your vows give you strength", None, tide=True, add=1, momentum_on_hit=1),
    ),
    ("honorbound", 2): (Boost("A hard truth", (SAA, COMPEL), add=1, momentum_on_hit=1),),
    ("honorbound", 3): (
        Boost(
            "Reroll one challenge die",
            (FULFILL,),
            reroll="one_challenge_on_miss",
            rerolled_miss=(MaxSpirit(-1),),
        ),
    ),
    ("improviser", 1): Reminder("Check Your Gear isn't a move in classic Ironsworn."),
    ("improviser", 2): (
        Boost(
            "An ad hoc tool",
            (SAA, FD),
            add=1,
            momentum_on_hit=1,
            late_add=1,
            late_cost=SUPPLY_COST,
        ),
    ),
    ("improviser", 3): (
        Boost("An impulsive move", None, add=2, momentum_on_strong=1, weak_as_miss=True),
    ),
    ("infiltrator", 1): (Boost("In enemy territory", None, add=1, momentum_on_hit=1),),
    ("infiltrator", 2): (
        Boost("Discover their plans", (GI,), roll=stat("shadow"), momentum_on_hit=1),
        Boost("Observe", (SAA,), roll=stat("shadow"), momentum_on_hit=1),
    ),
    ("infiltrator", 3): (
        Boost("Scavenge or loot", (RESUPPLY,), roll=stat("shadow"), on_hit=(SUPPLY_OR_MOMENTUM,)),
    ),
    ("lorekeeper", 1): (
        Boost("Lore from your studies", (SAA, GI), add=1, momentum_on_hit=1),
        Boost("Hours in the archive", (SAA, GI), add=2, momentum_on_hit=1),
    ),
    ("lorekeeper", 2): (
        Boost("Recover lost knowledge", (SWEAR,), reroll="any"),
        Boost("Recovered it", (FULFILL,), experience=1),
    ),
    ("lorekeeper", 3): Reminder(
        "One time only, an action rather than a move: /asset use lorekeeper."
    ),
    ("loyalist", 1): Reminder("Aid Your Ally is for play with an ally."),
    ("loyalist", 2): Reminder("Applies to an ally's move."),
    ("loyalist", 3): Reminder("Applies to an ally's move."),
    ("masked", 1): (
        Boost(
            "Wear your mask: +1",
            None,
            add=1,
            stat_field="material",
            on_one=(MaskTrack(-1),),
        ),
        Boost(
            "Wear your mask: +2",
            None,
            add=2,
            stat_field="material",
            on_one=(MaskTrack(-2),),
            needs=(2,),
        ),
    ),
    ("masked", 2): Reminder("Adds the +2 choice to the first ability."),
    ("masked", 3): (
        Boost("Wear your mask", (DEATH, DESOLATION), roll=RollWith("field", "material")),
    ),
    ("oathbreaker", 1): Reminder(
        "Counts as a debility. On a milestone for your marked vow, take +2 momentum with /adjust."
    ),
    ("oathbreaker", 2): (
        Boost("Reaffirm your commitment", (SAA, COMPEL), add=1, momentum_on_hit=1),
    ),
    ("oathbreaker", 3): (
        Boost(
            "Redemption",
            (FULFILL,),
            on_hit=(
                Choose(
                    tuple(
                        Option(
                            f"Improve {name} by +1 and discard Oathbreaker",
                            (RaiseStat(name), DiscardAsset("oathbreaker")),
                        )
                        for name in ("edge", "heart", "iron", "shadow", "wits")
                    ),
                    minimum=0,
                ),
            ),
        ),
    ),
    ("outcast", 1): AssetMove("scrape_by"),
    ("outcast", 2): (Boost("Your needs are few", (SOJOURN,), reroll="any", strong_as_weak=True),),
    ("outcast", 3): (Boost("Recall this place", (ARRIVE,), momentum_on_strong=2),),
    ("pretender", 1): AssetMove("establish_false_identity"),
    ("pretender", 2): (
        Boost("Under your false identity", (SOJOURN,), roll=stat("shadow"), momentum_on_hit=1),
    ),
    ("pretender", 3): (Boost("Reveal your true identity", (SAA,), reroll="any"),),
    ("revenant", 1): (Boost("At 0 health", (HARM, DEATH), add=1, on_burn=(Momentum(2),)),),
    ("revenant", 2): (Boost("A horror, spirit, or undead being", None, add=1),),
    ("revenant", 3): (
        Boost("Bring death", (END_FIGHT,), burn_progress=True, on_burn=(FollowUp(STRESS, 2),)),
    ),
    ("rider", 1): (
        Boost("Heal your horse", (HEAL,), add=1, momentum_on_hit=1),
        Boost("Calm or encourage your horse", (FD,), add=1, momentum_on_hit=1),
    ),
    ("rider", 2): (
        Boost(
            "Push your horse harder",
            (JOURNEY,),
            late_add=1,
            late_cost=(FollowUp(COMPANION_HARM, 1, "horse"),),
        ),
    ),
    ("rider", 3): (
        Boost("Size up from the saddle", (SAA,), add=1, roll=stat("wits"), momentum_on_hit=1),
    ),
    ("ritualist", 1): (Boost("Ready yourself for a ritual", (SAA,), add=1, momentum_on_hit=1),),
    ("ritualist", 2): (Boost("Spend supply on the ritual", RITUALS, before=SUPPLY_COST, add=1),),
    ("ritualist", 3): Reminder("Takes 1 experience off rituals, which /asset applies."),
    ("shadow_kin", 1): Reminder("Moves stat points once, when it's marked."),
    ("shadow_kin", 2): (Boost("Attuned to shadow", RITUALS, add=1),),
    ("shadow_kin", 3): (
        Boost("The sly ways of death", (DEATH,), roll=stat("shadow")),
        Boost("A deathbound quest", (SWEAR,), roll=stat("shadow"), reroll="any"),
        Boost("Fulfilled the deathbound quest", (FULFILL,), experience=2),
    ),
    ("sighted", 1): (Boost("Mystic forces", (FD, GI), add=1, momentum_on_hit=1),),
    ("sighted", 2): (
        Boost("A fellow mystic", (COMPEL, BOND, TEST_BOND), add=1, momentum_on_hit=1),
    ),
    ("sighted", 3): (
        Boost("Study someone", (SAA,), add=1, momentum_on_hit=1),
        Boost(
            "Pierce the veil",
            (SAA,),
            add=1,
            momentum_on_hit=1,
            reroll="any",
            weak_as_miss=True,
        ),
    ),
    ("slayer", 1): (
        Boost("Track a beast or horror", (GI,), add=1, momentum_on_hit=1),
        Boost("Ready yourself to fight them", (SAA,), add=1, momentum_on_hit=1),
    ),
    ("slayer", 2): (
        Boost("Slay a beast or horror", (SWEAR,), reroll="any"),
        Boost("Slew it", (FULFILL,), experience=1),
    ),
    ("slayer", 3): Reminder("Takes a trophy after a kill: /asset use slayer ritual|sojourn."),
    ("spirit_bound", 1): (
        Boost(
            "Consult the spirit",
            (SAA, GI),
            add=1,
            momentum_on_hit=2,
            on_weak=(FollowUp(STRESS, 1),),
        ),
    ),
    ("spirit_bound", 2): (
        Boost("Guided by the spirit", (DEATH,), add=1, on_strong=(GainExperience(1),)),
    ),
    ("spirit_bound", 3): (
        Boost(
            "In service to the spirit",
            (FULFILL,),
            limit="one_time",
            on_hit=(
                Choose(
                    (
                        Option(
                            "Let them go",
                            (ExperiencePerAbility("spirit_bound", 2), DiscardAsset("spirit_bound")),
                        ),
                        Option(
                            "Deepen your connection",
                            (Note("Add +1 more when you use this asset; press + when rolling."),),
                        ),
                    )
                ),
            ),
        ),
    ),
    ("storyweaver", 1): (
        Boost("An inspiring tale", (SAA, COMPEL, BOND), add=1, momentum_on_hit=1),
    ),
    ("storyweaver", 2): (
        Boost("Share a story", (CAMP,), on_option=(("Relax", (SPIRIT_OR_MOMENTUM,)),)),
    ),
    ("storyweaver", 3): (Boost("A community you share a bond with", (SOJOURN,), add=1),),
    ("trickster", 1): (Boost("Lie, bluff, steal, or cheat", (FD, SAA, COMPEL), add=1),),
    ("trickster", 2): (
        Boost("Investigate a devious scheme", (GI,), roll=stat("shadow"), momentum_on_hit=2),
    ),
    ("trickster", 3): (
        Boost("Keep your secret", (BOND,), roll=stat("shadow")),
        Boost(
            "Reveal the truth",
            (BOND,),
            roll=stat("heart"),
            weak_as_miss=True,
            on_strong=(MarkProgress("bonds"), GainExperience(1)),
        ),
    ),
    ("veteran", 1): (
        Boost(
            "Hard-won experience",
            None,
            on_burn=(Momentum(1), AddToNextMove(1)),
            burn_initiative=True,
        ),
    ),
    ("veteran", 2): (
        Boost("Someone who fought beside you", (SWEAR, BOND), add=2, momentum_on_hit=2),
    ),
    ("veteran", 3): (Boost("Loot the dead", (RESUPPLY,), add=1, momentum_on_hit=1),),
    ("waterborn", 1): (Boost("Your knowledge of water", (FD, GI, SAA), add=1, momentum_on_hit=1),),
    ("waterborn", 2): (
        Boost(
            "By boat or ship",
            (JOURNEY,),
            add=1,
            on_strong=(
                Choose(
                    (
                        Option("The wind is at your back", (MarkProgress("journey"),)),
                        Option("Find safe anchor", (Note("Make Camp now and reroll any dice."),)),
                        Option("Reap the bounty", (Note("Resupply now and reroll any dice."),)),
                    )
                ),
            ),
        ),
    ),
    ("waterborn", 3): (Boost("Aboard a boat or ship", (FRAY,), reroll="any"),),
    ("wayfinder", 1): (
        Boost("Find the way", (JOURNEY,), momentum_on_strong=1, on_burn=(Momentum(1),)),
    ),
    ("wayfinder", 2): (Boost("Survey or scout ahead", (SAA, GI), add=1, momentum_on_hit=1),),
    ("wayfinder", 3): (
        Boost("Guide someone safely", (SWEAR,), reroll="any"),
        Boost("Guided them", (FULFILL,), experience=1),
    ),
    ("weaponmaster", 1): (Boost("Size up your foe", (SAA,), add=1, momentum_on_hit=1),),
    ("weaponmaster", 2): Reminder("Takes 1 experience off combat talents, which /asset applies."),
    ("weaponmaster", 3): (
        Boost("A sudden change of weapon", (STRIKE,), tide=True, add=1, harm_on_strong=2),
    ),
    ("wildblood", 1): (Boost("Woodcraft", (FD, SAA, GI), add=1),),
    ("wildblood", 2): (
        Boost("Hide or sneak in the woodlands", (FD, SAA), add=1, momentum_on_hit=1),
    ),
    ("wildblood", 3): (
        Boost("Camp in the woodlands", (CAMP,), roll=stat("wits"), extra_choices=1),
    ),
    ("wright", 1): (
        Boost("Craft with your specialty", (SAA,), add=1, momentum_on_hit=1),
        Boost("Create or repair in peril", (FD,), add=1, momentum_on_hit=1),
    ),
    ("wright", 2): (Boost("Spend supply to add +1", (SAA, FD), late_add=1, late_cost=SUPPLY_COST),),
    ("wright", 3): (Boost("Your gift", (COMPEL, BOND, TEST_BOND), reroll="any", limit="one_time"),),
    # Rituals
    ("augur", 1): AssetMove("augur"),
    ("augur", 2): Reminder(UPGRADES_RESULT),
    ("augur", 3): _ritual("augur", "augur"),
    ("awakening", 1): AssetMove("awaken_simulacrum"),
    ("awakening", 2): Reminder("Raises the simulacrum's health to 6, which /asset applies."),
    ("awakening", 3): _ritual("awakening", "awaken_simulacrum"),
    ("bind", 1): AssetMove("bind"),
    ("bind", 2): Reminder(UPGRADES_RESULT),
    ("bind", 3): _ritual("bind", "bind"),
    ("communion", 1): AssetMove("commune"),
    ("communion", 2): Reminder("Lets you commune with the long-dead; there's nothing to roll."),
    ("communion", 3): _ritual("communion", "commune"),
    ("divination", 1): AssetMove("cast_runes"),
    ("divination", 2): Reminder("Lets the runes reveal the future; there's nothing to roll."),
    ("divination", 3): _ritual("divination", "cast_runes"),
    ("invoke", 1): AssetMove(
        "invoke",
        (
            Boost(
                "Minor mystical effects",
                (SAA, FD),
                roll=meter("essence"),
                before=(AssetMeterChange("invoke", "essence", -1),),
                momentum_on_hit=1,
            ),
        ),
    ),
    ("invoke", 2): (
        Boost(
            "A show of power",
            (COMPEL,),
            roll=meter("essence"),
            before=(AssetMeterChange("invoke", "essence", -1),),
        ),
    ),
    ("invoke", 3): _ritual("invoke", "invoke"),
    ("keen", 1): AssetMove("keen"),
    ("keen", 2): Reminder(UPGRADES_RESULT),
    ("keen", 3): _ritual("keen", "keen"),
    ("leech", 1): AssetMove("draw_blood_rune"),
    ("leech", 2): Reminder("Lets an ally or companion take the rune's leftover points."),
    ("leech", 3): _ritual("leech", "draw_blood_rune"),
    ("lightbearer", 1): AssetMove(
        "capture_light",
        (
            Boost(
                "Light against darkness",
                None,
                add=2,
                before=(AssetMeterChange("lightbearer", "light", -1),),
            ),
        ),
    ),
    ("lightbearer", 2): (
        Boost("Unleash your light", ATTACKS, roll=meter("light"), unleash="light"),
    ),
    ("lightbearer", 3): _ritual("lightbearer", "capture_light"),
    ("scry", 1): AssetMove("scry"),
    ("scry", 2): Reminder("Lets you study a past event; there's nothing to roll."),
    ("scry", 3): _ritual("scry", "scry"),
    ("shadow_walk", 1): AssetMove("shadow_walk"),
    ("shadow_walk", 2): (
        Boost(
            "The hidden paths",
            (JOURNEY,),
            roll=stat("shadow"),
            after=(FollowUp(STRESS, 1),),
            on_strong=(MarkProgress("journey"),),
        ),
    ),
    ("shadow_walk", 3): _ritual("shadow_walk", "shadow_walk"),
    ("sway", 1): AssetMove("sway"),
    ("sway", 2): Reminder(UPGRADES_RESULT),
    ("sway", 3): _ritual("sway", "sway"),
    ("talisman", 1): AssetMove("fashion_talisman"),
    ("talisman", 2): Reminder("Lets the charm protect against all supernatural threats."),
    ("talisman", 3): _ritual("talisman", "fashion_talisman"),
    ("tether", 1): AssetMove(
        "tether",
        (
            Boost("Return, tethered: heart", (JOURNEY,), roll=stat("heart"), momentum_on_hit=1),
            Boost(
                "Return, tethered: spirit",
                (JOURNEY,),
                roll=RollWith("condition", "spirit"),
                momentum_on_hit=1,
            ),
            Boost("Arrive, tethered", (ARRIVE,), momentum_on_strong=2),
        ),
    ),
    ("tether", 2): (Boost("Sojourn in the tethered place", (SOJOURN,), reroll="any"),),
    ("tether", 3): _ritual("tether", "tether"),
    ("totem", 1): AssetMove("focus_totem"),
    ("totem", 2): Reminder("Lets you perceive through your companion's senses."),
    ("totem", 3): _ritual("totem", "focus_totem"),
    ("visage", 1): AssetMove("paint_visage"),
    ("visage", 2): Reminder(UPGRADES_RESULT),
    ("visage", 3): _ritual("visage", "paint_visage"),
    ("ward", 1): AssetMove("ward"),
    ("ward", 2): Reminder(UPGRADES_RESULT),
    ("ward", 3): _ritual("ward", "ward"),
}


@dataclass(frozen=True)
class BoostRef:
    """Which boost the player turned on: an asset, its ability from 1 to 3, and the variant.

    Attributes:
        asset: The asset id.
        ability: The ability, from 1 to 3.
        variant: The index of the boost in the ability's entry, for an ability with a choice.
        lasting: For a lasting effect, its index in the campaign's list; the asset and
            ability are then those of the effect's source, or empty.
    """

    asset: str
    ability: int
    variant: int = 0
    lasting: int | None = None


@dataclass(frozen=True)
class AvailableBoost:
    """A boost the character has, with the names to show it by.

    Attributes:
        ref: Which boost it is.
        asset_name: The asset's name, such as "Archer".
        boost: The boost.
    """

    ref: BoostRef
    asset_name: str
    boost: Boost

    @property
    def label(self) -> str:
        """The asset, the ability, and the boost, such as "Archer 1: Trust your instincts".

        A lasting effect is shown by its own name.
        """
        if self.ref.lasting is not None:
            return self.boost.label
        return f"{self.asset_name} {self.ref.ability}: {self.boost.label}"


def entry_boosts(entry: Entry) -> tuple[Boost, ...]:
    """Return the boosts an entry gives: its own, an asset move's, or none for a reminder."""
    if isinstance(entry, AssetMove):
        return entry.boosts
    if isinstance(entry, Reminder):
        return ()
    return entry


def final_hit(hit: Hit, boosts: Iterable[Boost]) -> Hit:
    """Apply "count a weak hit as a miss" and "a strong hit counts as a weak hit"."""
    boosts = tuple(boosts)
    if hit is Hit.STRONG and any(boost.strong_as_weak for boost in boosts):
        return Hit.WEAK
    if hit is Hit.WEAK and any(boost.weak_as_miss for boost in boosts):
        return Hit.MISS
    return hit


def boosted_harm(harm: int, hit: Hit, boosts: Iterable[Boost], *, burned: bool) -> int:
    """Return the harm a hit inflicts with the boosts: a set harm, then any extra harm."""
    boosts = tuple(boosts)
    for boost in boosts:
        if boost.set_harm is not None:
            harm = boost.set_harm
    if hit is Hit.MISS:
        return harm
    harm += sum(boost.harm for boost in boosts)
    if hit is Hit.STRONG:
        harm += sum(boost.harm_on_strong for boost in boosts)
    if burned:
        harm += sum(boost.burn_harm for boost in boosts)
    return harm


@dataclass(frozen=True)
class RollFacts:
    """What happened on the roll, which decides the boosts' effects.

    Attributes:
        hit: The result, after any downgrade.
        match: True when the challenge dice match.
        action_die: The action die, or None for a progress roll or an automatic hit.
        rolled_with: What the roll used, such as `heart`.
        burned: True when the player burned momentum.
        rerolled: True when the player rerolled.
        late: True when the player took a late add.
    """

    hit: Hit
    match: bool = False
    action_die: int | None = None
    rolled_with: str = ""
    burned: bool = False
    rerolled: bool = False
    late: bool = False


def boost_effects(boost: Boost, facts: RollFacts) -> tuple[Effect, ...]:
    """Return the effects a boost adds to the result, in order."""
    if boost.rolled is not None and boost.rolled != facts.rolled_with:
        return ()
    hit = facts.hit
    effects: list[Effect] = []
    if hit is not Hit.MISS:
        if boost.momentum_on_hit:
            effects.append(Momentum(boost.momentum_on_hit))
        effects += boost.on_hit
    if hit is Hit.STRONG:
        if boost.momentum_on_strong:
            effects.append(Momentum(boost.momentum_on_strong))
        effects += boost.on_strong
        if facts.match:
            effects += boost.on_strong_match
    if hit is Hit.WEAK:
        effects += boost.on_weak
    if hit is Hit.MISS:
        effects += boost.on_miss
        if facts.rerolled:
            effects += boost.rerolled_miss
    if facts.action_die == 1:
        effects += boost.on_one
    if facts.burned:
        effects += boost.on_burn
    if facts.late:
        effects += boost.late_cost
    effects += boost.after
    return tuple(effects)


def adjust_outcome(
    effects: tuple[Effect, ...], boosts: Iterable[Boost], hit: Hit
) -> tuple[Effect, ...]:
    """Change a result's own effects: add to chosen options, offer more choices, and add
    experience where Fulfill Your Vow marks it."""
    boosts = tuple(boosts)
    extra = sum(boost.extra_choices for boost in boosts) if hit is not Hit.MISS else 0
    additions = [addition for boost in boosts for addition in boost.on_option]
    experience = sum(boost.experience for boost in boosts)
    adjusted: list[Effect] = []
    for effect in effects:
        if isinstance(effect, Choose):
            options = tuple(
                Option(
                    option.label,
                    option.effects
                    + tuple(
                        e
                        for prefix, added in additions
                        if option.label.startswith(prefix)
                        for e in added
                    ),
                )
                for option in effect.options
            )
            count = min(len(options), effect.count + extra)
            minimum = min(count, effect.minimum + extra) if effect.minimum else 0
            adjusted.append(Choose(options, count=count, minimum=minimum))
        else:
            adjusted.append(effect)
        if isinstance(effect, MarkExperience) and experience:
            adjusted.append(GainExperience(experience))
    return tuple(adjusted)


type Expiry = Literal["use", "one", "low", "manual"]
"""When a lasting effect ends: after one use, when the action die is a 1 on a move that
uses it, when health, spirit, or momentum falls below +1, or when the player ends it."""


@dataclass(frozen=True)
class LastingKind:
    """A kind of lasting effect: what it does to a move and when it ends.

    Attributes:
        boost: What it does when the player turns it on, like an ability's boost. Its label
            names the effect.
        expires: When it ends.
    """

    boost: Boost
    expires: Expiry


_MAGIC_SPENT = "The magic is spent."

LASTING: dict[str, LastingKind] = {
    "seeker_arrow": LastingKind(Boost("Seeker arrow", ATTACKS, reroll="any"), "use"),
    "ravager_arrow": LastingKind(
        Boost("Ravager arrow", ATTACKS, on_hit=(InflictRolledHarm(),)), "use"
    ),
    "carved_rune": LastingKind(Boost("Carved rune", ATTACKS, on_hit=(InflictRolledHarm(),)), "use"),
    "elixir": LastingKind(Boost("Elixir", None, add=1), "low"),
    "pelt": LastingKind(Boost("Pelt", None, add=1, on_one=(Note(_MAGIC_SPENT),)), "one"),
    "beast_pelt": LastingKind(
        Boost("Beast pelt", None, add=2, on_one=(Note(_MAGIC_SPENT),)), "one"
    ),
    "keen": LastingKind(Boost("Keen", ATTACKS, harm=1, on_one=(Note(_MAGIC_SPENT),)), "one"),
    "keen_once": LastingKind(
        Boost("Keen, one time only", (CIRCLE, FRAY, BATTLE), add=1, momentum_on_hit=2), "use"
    ),
    "blood_rune": LastingKind(
        Boost(
            "Blood rune",
            None,
            reroll="any",
            harm=2,
            on_hit=(Note("Take +1 health or +1 momentum for each point of harm inflicted."),),
            after=(AssetDebility("leech", on=False),),
        ),
        "use",
    ),
    "false_identity_2": LastingKind(
        Boost("False identity", None, add=2, on_one=(Note("Someone doubts you."),)), "manual"
    ),
    "false_identity_1": LastingKind(
        Boost("False identity", None, add=1, on_one=(Note("Someone doubts you."),)), "manual"
    ),
    "augur": LastingKind(Boost("The crows' guidance", (JOURNEY,), add=1), "use"),
    "simulacrum": LastingKind(Boost("Your simulacrum's aid", None, add=2), "manual"),
    "simulacrum_wild": LastingKind(
        Boost(
            "Your simulacrum's aid",
            None,
            add=2,
            on_one=(Note("Face Danger +heart to keep it from turning on you (formidable)."),),
        ),
        "manual",
    ),
    "commune": LastingKind(Boost("Speaking with the spirit", None, add=1), "manual"),
    "runes": LastingKind(Boost("The runes' reading", (GI, COMPEL, BOND), add=1), "manual"),
    "shadow_walk": LastingKind(Boost("The shadow veil", None, reroll="any"), "use"),
    "sway": LastingKind(Boost("The wind's whisper", (COMPEL,), reroll="any"), "use"),
    "sway_upgraded": LastingKind(
        Boost(
            "The wind's whisper",
            (COMPEL,),
            reroll="any",
            on_strong=(AddLasting("sway_gather"),),
        ),
        "use",
    ),
    "sway_gather": LastingKind(Boost("The wind's whisper", (GI,), reroll="any"), "use"),
    "talisman_2": LastingKind(Boost("Talisman", None, add=2, on_one=(Note(_MAGIC_SPENT),)), "one"),
    "talisman_1": LastingKind(Boost("Talisman", None, add=1, on_one=(Note(_MAGIC_SPENT),)), "one"),
    "totem": LastingKind(
        Boost("Totem", None, add=1, momentum_on_hit=1, on_one=(Note(_MAGIC_SPENT),)), "one"
    ),
    "visage": LastingKind(
        Boost("Visage", (SAA, COMPEL), add=2, momentum_on_hit=1, on_one=(Note(_MAGIC_SPENT),)),
        "one",
    ),
    "visage_attack": LastingKind(
        Boost("Visage", (STRIKE, CLASH, BATTLE), add=1, on_one=(Note(_MAGIC_SPENT),)), "one"
    ),
    "ward_harm": LastingKind(Boost("Ward", None, harm=1), "use"),
    "ward_harm_2": LastingKind(Boost("Ward", None, harm=2), "use"),
    "trophy_ritual": LastingKind(Boost("Trophy", RITUALS, reroll="any"), "use"),
    "trophy_sojourn": LastingKind(Boost("Trophy", (SOJOURN,), reroll="any"), "use"),
    "audience": LastingKind(Boost("Your audience", None, add=2), "use"),
    "spider_reflection": LastingKind(Boost("Your spider's reflection", (GI,), reroll="any"), "use"),
}
