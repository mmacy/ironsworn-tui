"""What each move's result does to the campaign, as lists of effects.

Datasworn's outcome text is prose, so this table is written by hand from it. Where the text says
something the effects can't express, the entry has a [`Note`][ironsworn_tui.outcomes.Note], and
the player applies it with `/adjust`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from ironsworn_tui.campaign import Debility, Meter
from ironsworn_tui.moves import Initiative
from ironsworn_tui.rules.datasworn import Stat
from ironsworn_tui.rules.dice import Hit

type Track = Literal["vow", "journey", "target", "bonds"]
"""A progress track: the move's vow, the journey, the targeted foe, or the bonds track."""


@dataclass(frozen=True)
class Momentum:
    """Take or suffer momentum."""

    amount: int


@dataclass(frozen=True)
class MeterChange:
    """Take or suffer health, spirit, or supply."""

    meter: Meter
    amount: int


@dataclass(frozen=True)
class MarkProgress:
    """Mark progress on a track. For the targeted foe, `times` is the harm inflicted."""

    track: Track
    times: int = 1


@dataclass(frozen=True)
class SetInitiative:
    """Give initiative to the character or the foe."""

    who: Initiative


@dataclass(frozen=True)
class FollowUp:
    """A move the result calls for, such as Pay the Price or Endure Harm.

    Attributes:
        move: The move id.
        amount: The harm or stress, for Endure Harm, Endure Stress, and Companion Endure
            Harm.
        asset: The companion, for Companion Endure Harm.
    """

    move: str
    amount: int | None = None
    asset: str | None = None


@dataclass(frozen=True)
class ClearDebility:
    """Clear a debility, as Heal and Sojourn can."""

    debility: Debility


@dataclass(frozen=True)
class MarkDebility:
    """Mark a debility, as a miss at 0 on Endure Harm or Endure Stress can."""

    debility: Debility


@dataclass(frozen=True)
class RollTable:
    """Roll on an oracle table and show the result."""

    table_id: str


@dataclass(frozen=True)
class AddToNextMove:
    """Add to the next move, as "Make another move now and add +1" says."""

    amount: int


@dataclass(frozen=True)
class MarkExperience:
    """Mark experience for the move's vow: its rank, minus `less`."""

    less: int = 0


@dataclass(frozen=True)
class CompleteVow:
    """Remove the move's vow from the active vows."""


@dataclass(frozen=True)
class Recommit:
    """Clear all but one box of the move's track and raise its rank, as a recommitment does."""

    track: Literal["vow", "journey"]


@dataclass(frozen=True)
class EndJourney:
    """End the active journey."""


@dataclass(frozen=True)
class RemoveTarget:
    """Take the targeted foe out of the fight."""


@dataclass(frozen=True)
class Note:
    """Outcome text the effects can't express. The roll card shows it."""

    text: str


@dataclass(frozen=True)
class InflictHarm:
    """Inflict harm on the targeted foe: mark progress on its track once per point.

    Attributes:
        amount: The harm, or None for the character's usual harm.
    """

    amount: int | None = None


@dataclass(frozen=True)
class AssetMeterChange:
    """Add to or take from an asset's meter, such as a warband's strength."""

    asset: str
    meter: str
    amount: int


@dataclass(frozen=True)
class AssetMeterFromRank:
    """Add the vow's rank to an asset's meter, as Fortune Hunter's payment does."""

    asset: str
    meter: str


@dataclass(frozen=True)
class GainExperience:
    """Take experience."""

    amount: int


@dataclass(frozen=True)
class ExperiencePerAbility:
    """Take experience for each marked ability of an asset, as Spirit-bound's release does."""

    asset: str
    amount: int


@dataclass(frozen=True)
class MomentumFromMeter:
    """Take momentum equal to a meter: the character's health, or an asset's meter.

    Attributes:
        meter: The meter, such as `health`.
        asset: The asset whose meter it is, or None for the character's.
    """

    meter: str
    asset: str | None = None


@dataclass(frozen=True)
class AssetDebility:
    """Make an asset count as a debility, or stop it counting."""

    asset: str
    on: bool


@dataclass(frozen=True)
class RaiseStat:
    """Raise a stat by 1."""

    stat: Stat


@dataclass(frozen=True)
class DiscardAsset:
    """Remove an asset from the character."""

    asset: str


@dataclass(frozen=True)
class MaxSpirit:
    """Raise or lower the character's maximum spirit, as Honorbound does."""

    amount: int


@dataclass(frozen=True)
class AddLasting:
    """Start a lasting effect, such as a talisman, that later moves can use.

    Attributes:
        kind: The kind of effect, a key of
            [`LASTING`][ironsworn_tui.abilities.LASTING].
        stat: The stat it's tied to, for an elixir or a pelt.
    """

    kind: str
    stat: Stat | None = None


@dataclass(frozen=True)
class SetAssetMeter:
    """Set an asset's meter: to a value, or to its maximum when the value is None."""

    asset: str
    meter: str
    value: int | None = None


@dataclass(frozen=True)
class AssetMeterFromActionDie:
    """Add the action die's value to an asset's meter, as Invoke's essence does."""

    asset: str
    meter: str


@dataclass(frozen=True)
class CompanionHealth:
    """Give or take companion health.

    Attributes:
        amount: The health.
        every: True for every companion, as Make Camp's "you and any companions"; False for
            the companion the move is about, as in Companion Endure Harm.
    """

    amount: int
    every: bool = True


@dataclass(frozen=True)
class InflictRolledHarm:
    """Inflict 1d6 extra harm on the targeted foe, as a Ravager arrow or a carved rune does."""


@dataclass(frozen=True)
class MaskTrack:
    """Take from the meter a Masked character's mask is tied to: health or spirit."""

    amount: int


@dataclass(frozen=True)
class Option:
    """One choice on the roll card, with its effects."""

    label: str
    effects: tuple[Effect, ...]


@dataclass(frozen=True)
class FoeHarmForFight:
    """Add to each foe's harm until the fight ends, as Draw the Circle's "Bare yourself" does."""

    amount: int


@dataclass(frozen=True)
class HarmForFight:
    """Set the character's harm until the fight ends, as Draw the Circle's "Hold no iron" does."""

    harm: int


@dataclass(frozen=True)
class Choose:
    """A choice for the player: `minimum` to `count` of the options, each once."""

    options: tuple[Option, ...]
    count: int = 1
    minimum: int = 1


type Effect = (
    Momentum
    | MeterChange
    | MarkProgress
    | SetInitiative
    | FollowUp
    | ClearDebility
    | MarkDebility
    | RollTable
    | AddToNextMove
    | MarkExperience
    | CompleteVow
    | Recommit
    | EndJourney
    | RemoveTarget
    | Note
    | Choose
    | InflictHarm
    | AssetMeterChange
    | AssetMeterFromRank
    | GainExperience
    | ExperiencePerAbility
    | MomentumFromMeter
    | AssetDebility
    | RaiseStat
    | DiscardAsset
    | MaxSpirit
    | MaskTrack
    | AddLasting
    | SetAssetMeter
    | AssetMeterFromActionDie
    | CompanionHealth
    | InflictRolledHarm
    | FoeHarmForFight
    | HarmForFight
)

PAY_THE_PRICE = FollowUp("pay_the_price")


@dataclass(frozen=True)
class MoveDetails:
    """Facts about the move being made that change its outcome.

    Attributes:
        heal_self: For Heal, True when the character mends their own wounds.
        harm: The harm the character inflicts: 2 with a deadly weapon, 1 without one
            (rulebook page 19).
        foe_harm: The targeted foe's harm, for Endure Harm after End the Fight.
        meter_above_zero: For Endure Harm or Stress, True when the meter is above 0, so
            "Shake it off" is allowed.
        upgraded: For an asset move, True when the asset's second ability is marked, which
            most rituals' second abilities use to change the result.
        bond: For Sojourn, True when the character shares a bond with the community, so they
            choose one more (rulebook page 71).
    """

    heal_self: bool = True
    harm: int = 2
    foe_harm: int = 1
    meter_above_zero: bool = True
    upgraded: bool = False
    bond: bool = False


def _option(label: str, *effects: Effect) -> Option:
    return Option(label=label, effects=effects)


def _face_danger(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Momentum(1),)
        case Hit.WEAK:
            return (
                Choose(
                    (
                        _option("Delayed, lose advantage, or new danger", Momentum(-1)),
                        _option("Tired or hurt", FollowUp("endure_harm", 1)),
                        _option("Dispirited or afraid", FollowUp("endure_stress", 1)),
                        _option("Sacrifice resources", MeterChange("supply", -1)),
                    )
                ),
            )
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _secure_an_advantage(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (
                Choose(
                    (
                        _option("Take control: +1 on your next move", AddToNextMove(1)),
                        _option("Prepare to act", Momentum(2)),
                    )
                ),
            )
        case Hit.WEAK:
            return (Momentum(1),)
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _aid_your_ally(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    # The ally takes Secure an Advantage's benefits, and the app doesn't track the ally.
    match hit:
        case Hit.STRONG:
            return (Note("Your ally takes +1 on their next move, or +2 momentum."),)
        case Hit.WEAK:
            return (Note("Your ally takes +1 momentum."),)
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _gather_information(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    return {Hit.STRONG: (Momentum(2),), Hit.WEAK: (Momentum(1),), Hit.MISS: (PAY_THE_PRICE,)}[hit]


def _heal(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    if hit is Hit.MISS:
        return (PAY_THE_PRICE,)
    if details.heal_self:
        care: tuple[Effect, ...] = (ClearDebility("wounded"), MeterChange("health", 2))
    else:
        care = (Note("If they're wounded, they may clear it. Give them up to +2 health."),)
    if hit is Hit.STRONG:
        return care
    cost = Choose(
        (
            _option("Suffer -1 supply", MeterChange("supply", -1)),
            _option("Suffer -1 momentum", Momentum(-1)),
        )
    )
    return (*care, cost)


def _resupply(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (MeterChange("supply", 2),)
        case Hit.WEAK:
            return (
                Choose(
                    (
                        _option(
                            "Take +1 supply for -1 momentum", MeterChange("supply", 1), Momentum(-1)
                        ),
                        _option(
                            "Take +2 supply for -2 momentum", MeterChange("supply", 2), Momentum(-2)
                        ),
                        _option("Take nothing"),
                    )
                ),
            )
        case Hit.MISS:
            return (PAY_THE_PRICE,)


_CAMP = (
    _option("Recuperate: +1 health", MeterChange("health", 1), CompanionHealth(1)),
    _option(
        "Partake: -1 supply, +1 health",
        MeterChange("supply", -1),
        MeterChange("health", 1),
        CompanionHealth(1),
    ),
    _option("Relax: +1 spirit", MeterChange("spirit", 1)),
    _option("Focus: +1 momentum", Momentum(1)),
    _option(
        "Prepare: +1 on your next journey",
        Note("Add +1 when you break camp and Undertake a Journey."),
    ),
)


def _make_camp(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Choose(_CAMP, count=2, minimum=2),)
        case Hit.WEAK:
            return (Choose(_CAMP),)
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _undertake_a_journey(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (
                Choose(
                    (
                        _option("Make good use of your resources", MarkProgress("journey")),
                        _option(
                            "Move at speed: +1 momentum, -1 supply",
                            MarkProgress("journey"),
                            Momentum(1),
                            MeterChange("supply", -1),
                        ),
                    )
                ),
            )
        case Hit.WEAK:
            return (MarkProgress("journey"), MeterChange("supply", -1))
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _reach_your_destination(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (
                EndJourney(),
                Choose(
                    (
                        _option("Make another move now and add +1", AddToNextMove(1)),
                        _option("Take +1 momentum", Momentum(1)),
                    )
                ),
            )
        case Hit.WEAK:
            return (EndJourney(), Note("You arrive but face an unforeseen hazard or complication."))
        case Hit.MISS:
            return (
                Choose(
                    (
                        _option("The journey continues", Recommit("journey")),
                        _option("The journey ends", EndJourney()),
                    )
                ),
            )


def _compel(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Momentum(1), Note("If you Gather Information from this exchange, add +1."))
        case Hit.WEAK:
            return (Momentum(1), Note("They ask something of you in return."))
        case Hit.MISS:
            return (PAY_THE_PRICE,)


_SOJOURN = (
    _option("Mend: clear wounded, +1 health", ClearDebility("wounded"), MeterChange("health", 1)),
    _option("Hearten: clear shaken, +1 spirit", ClearDebility("shaken"), MeterChange("spirit", 1)),
    _option(
        "Equip: clear unprepared, +1 supply", ClearDebility("unprepared"), MeterChange("supply", 1)
    ),
    _option("Recuperate: +2 health", MeterChange("health", 2), CompanionHealth(2)),
    _option("Consort: +2 spirit", MeterChange("spirit", 2)),
    _option("Provision: +2 supply", MeterChange("supply", 2)),
    _option("Plan: +2 momentum", Momentum(2)),
    _option(
        "Take a quest",
        Note("Envision what the community needs. If you help, Swear an Iron Vow and add +1."),
    ),
)
_SOJOURN_FOCUS = Note(
    "You may focus on one recover action and roll +heart again: +2 more on a strong hit, +1 "
    "more on a weak hit, and on a miss you lose that action's benefits. If you share a bond, "
    "add +1."
)


def _sojourn(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            count = 3 if details.bond else 2
            return (Choose(_SOJOURN, count=count, minimum=count), _SOJOURN_FOCUS)
        case Hit.WEAK:
            count = 2 if details.bond else 1
            return (Choose(_SOJOURN, count=count, minimum=count), _SOJOURN_FOCUS)
        case Hit.MISS:
            return (PAY_THE_PRICE,)


_BOASTS = (
    _option("Grant first strike: your foe has initiative", Momentum(1), SetInitiative("foe")),
    _option("Bare yourself: your foe's harm is +1", Momentum(1), FoeHarmForFight(1)),
    _option("Hold no iron: your harm is 1", Momentum(1), HarmForFight(1)),
    _option("Bloody yourself: Endure Harm (1 harm)", Momentum(1), FollowUp("endure_harm", 1)),
    _option("To the death", Momentum(1), Note("This fight must end with death.")),
)


def _draw_the_circle(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            # The rulebook allows up to three boasts (page 73). Datasworn says two.
            return (Momentum(1), Choose(_BOASTS, count=3, minimum=0))
        case Hit.WEAK:
            return (Choose(_BOASTS, minimum=0),)
        case Hit.MISS:
            return (SetInitiative("foe"), PAY_THE_PRICE)


_SPIRIT_OR_MOMENTUM = Choose(
    (_option("Take +1 spirit", MeterChange("spirit", 1)), _option("Take +2 momentum", Momentum(2)))
)


def _forge_a_bond(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (MarkProgress("bonds"), _SPIRIT_OR_MOMENTUM)
        case Hit.WEAK:
            return (
                Note("They ask something more of you first. Envision it, and do it or swear to."),
                Choose(
                    (
                        _option(
                            "You do it, or Swear an Iron Vow: mark the bond", MarkProgress("bonds")
                        ),
                        _option("You refuse or fail: Pay the Price", PAY_THE_PRICE),
                    )
                ),
            )
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _test_your_bond(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (_SPIRIT_OR_MOMENTUM,)
        case Hit.WEAK:
            return (
                Note("Your bond is fragile. Envision what they ask of you."),
                Choose(
                    (
                        _option("You do it, or Swear an Iron Vow"),
                        _option(
                            "You refuse or fail: clear the bond and Pay the Price",
                            Note("Clear the bond."),
                            PAY_THE_PRICE,
                        ),
                    )
                ),
            )
        case Hit.MISS:
            return (Note("Clear the bond."), PAY_THE_PRICE)


def _swear_an_iron_vow(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Momentum(2),)
        case Hit.WEAK:
            return (Momentum(1),)
        case Hit.MISS:
            return (
                Choose(
                    (
                        _option("Press on: -2 momentum", Momentum(-2)),
                        _option("Give up: Forsake Your Vow", FollowUp("forsake_your_vow")),
                    )
                ),
            )


def _fulfill_your_vow(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (MarkExperience(), CompleteVow())
        case Hit.WEAK:
            return (
                MarkExperience(less=1),
                CompleteVow(),
                Note(
                    "There is more to be done. You may Swear an Iron Vow to set things right, and "
                    "add +1."
                ),
            )
        case Hit.MISS:
            return (
                Choose(
                    (
                        _option("Recommit", Recommit("vow")),
                        _option("Give up: Forsake Your Vow", FollowUp("forsake_your_vow")),
                    )
                ),
            )


def _enter_the_fray(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Momentum(2), SetInitiative("character"))
        case Hit.WEAK:
            return (
                Choose(
                    (
                        _option(
                            "Bolster your position: +2 momentum", Momentum(2), SetInitiative("foe")
                        ),
                        _option("Prepare to act: take initiative", SetInitiative("character")),
                    )
                ),
            )
        case Hit.MISS:
            return (PAY_THE_PRICE, SetInitiative("foe"))


def _strike(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (MarkProgress("target", times=details.harm + 1), SetInitiative("character"))
        case Hit.WEAK:
            return (MarkProgress("target", times=details.harm), SetInitiative("foe"))
        case Hit.MISS:
            return (PAY_THE_PRICE, SetInitiative("foe"))


def _clash(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (
                MarkProgress("target", times=details.harm),
                SetInitiative("character"),
                Choose(
                    (
                        _option("Bolster your position: +1 momentum", Momentum(1)),
                        _option("Find an opening: +1 harm", MarkProgress("target")),
                    )
                ),
            )
        case Hit.WEAK:
            return (MarkProgress("target", times=details.harm), PAY_THE_PRICE, SetInitiative("foe"))
        case Hit.MISS:
            return (PAY_THE_PRICE, SetInitiative("foe"))


def _battle(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Momentum(2), Note("You achieve your objective unconditionally."))
        case Hit.WEAK:
            return (Note("You achieve your objective, but not without cost."), PAY_THE_PRICE)
        case Hit.MISS:
            return (Note("You are defeated, and the objective is lost to you."), PAY_THE_PRICE)


def _write_your_epilogue(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    return (
        Note(
            {
                Hit.STRONG: "Things come to pass as you hoped.",
                Hit.WEAK: "Your life takes an unexpected turn, but not necessarily for the worse.",
                Hit.MISS: "Your fears are realized.",
            }[hit]
        ),
    )


def _end_the_fight(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (RemoveTarget(),)
        case Hit.WEAK:
            return (
                RemoveTarget(),
                Choose(
                    (
                        _option(
                            "It's worse than you thought: Endure Harm",
                            FollowUp("endure_harm", details.foe_harm),
                        ),
                        _option(
                            "You are overcome: Endure Stress",
                            FollowUp("endure_stress", details.foe_harm),
                        ),
                        _option(
                            "Your victory is short-lived",
                            Note("A new danger or foe appears, or an existing danger worsens."),
                        ),
                        _option(
                            "You suffer collateral damage",
                            Note(
                                "Something of value is lost or broken, or someone important must "
                                "pay the cost."
                            ),
                        ),
                        _option("You'll pay for it", Note("An objective falls out of reach.")),
                        _option("Others won't forget", Note("You are marked for vengeance.")),
                    )
                ),
            )
        case Hit.MISS:
            return (Note("You have lost this fight."), PAY_THE_PRICE)


def _endure(meter: Meter, embrace: str) -> OutcomeRule:
    def rule(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
        match hit:
            case Hit.STRONG:
                options = [_option(f"{embrace}: +1 momentum", Momentum(1))]
                if details.meter_above_zero:
                    shake = _option(
                        f"Shake it off: -1 momentum, +1 {meter}",
                        Momentum(-1),
                        MeterChange(meter, 1),
                    )
                    options.insert(0, shake)
                return (Choose(tuple(options)),)
            case Hit.WEAK:
                return ()
            case Hit.MISS:
                return (Momentum(-1),)

    return rule


def _face_death(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    return (
        Note(
            {
                Hit.STRONG: "Death rejects you. You are cast back into the mortal world.",
                Hit.WEAK: (
                    "You die making a noble sacrifice, or Death demands a quest: Swear an Iron "
                    "Vow (formidable or extreme), and mark cursed."
                ),
                Hit.MISS: "You are dead.",
            }[hit]
        ),
    )


def _face_desolation(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    return (
        Note(
            {
                Hit.STRONG: "You resist and press on.",
                Hit.WEAK: (
                    "Your spirit breaks after a noble sacrifice, or you see a dreaded vision: "
                    "Swear an Iron Vow (formidable or extreme) to prevent it, and mark tormented."
                ),
                Hit.MISS: "You succumb to despair or horror and are lost.",
            }[hit]
        ),
    )


type OutcomeRule = Callable[[Hit, MoveDetails], tuple[Effect, ...]]


# Companion Endure Harm and the moves asset abilities add. Each "As above, and ..." second
# ability that changes a result reads `details.upgraded`.


def _companion_endure_harm(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (CompanionHealth(1, every=False),)
        case Hit.WEAK:
            return (Note("If their health is 0, they can't help you until they have at least +1."),)
        case Hit.MISS:
            return (
                Momentum(-1),
                Note(
                    "If their health is 0, they are gravely wounded and out of action, and die "
                    "in an hour or two without aid."
                ),
            )


def _ritual(strong: tuple[Effect, ...], weak_cost: tuple[Effect, ...] = ()) -> OutcomeRule:
    """A ritual whose weak hit is its strong hit plus a cost."""

    def rule(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
        match hit:
            case Hit.STRONG:
                return strong
            case Hit.WEAK:
                return (*weak_cost, *strong)
            case Hit.MISS:
                return (PAY_THE_PRICE,)

    return rule


def _upgraded_ritual(
    strong: tuple[Effect, ...], upgrade: tuple[Effect, ...], weak_cost: tuple[Effect, ...] = ()
) -> OutcomeRule:
    """A ritual whose second ability adds effects to a hit."""

    def rule(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
        effects = (*strong, *upgrade) if details.upgraded else strong
        return _ritual(effects, weak_cost)(hit, details)

    return rule


_STATS: tuple[Stat, ...] = ("edge", "heart", "iron", "shadow", "wits")
_ELIXIRS: dict[Stat, str] = {
    "edge": "Deftness",
    "heart": "Audacity",
    "iron": "Vigor",
    "shadow": "Slyness",
    "wits": "Clarity",
}
_PELTS: dict[Stat, str] = {
    "edge": "Wolf",
    "iron": "Bear",
    "heart": "Deer",
    "shadow": "Fox",
    "wits": "Boar",
}


def _craft_arrow(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    seeker, ravager = AddLasting("seeker_arrow"), AddLasting("ravager_arrow")
    match hit:
        case Hit.STRONG:
            return (seeker, ravager)
        case Hit.WEAK:
            return (Choose((_option("Seeker", seeker), _option("Ravager", ravager))),)
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _create_elixir(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    if hit is Hit.MISS:
        return (PAY_THE_PRICE,)
    options = tuple(
        _option(f"{name} ({stat})", AddLasting("elixir", stat)) for stat, name in _ELIXIRS.items()
    )
    count = 1
    if details.upgraded:
        # Alchemist's second ability: two effects in one dose, or two doses of one.
        count = 2
        options += tuple(
            _option(f"Two doses of {name} ({stat})", *[AddLasting("elixir", stat)] * 2)
            for stat, name in _ELIXIRS.items()
        )
    choose = Choose(options, count=count, minimum=1)
    if hit is Hit.WEAK:
        return (MeterChange("supply", -1), choose)
    return (choose,)


def _commemorate(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Momentum(2), MeterChange("spirit", 1))
        case Hit.WEAK:
            return (
                Choose(
                    (
                        _option("Take +1 momentum", Momentum(1)),
                        _option("Take +1 spirit", MeterChange("spirit", 1)),
                    )
                ),
            )
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _scrape_by(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (MeterChange("supply", 1),)
        case Hit.WEAK:
            return (
                Choose(
                    (_option("-2 momentum for +1 supply", Momentum(-2), MeterChange("supply", 1)),),
                    minimum=0,
                ),
            )
        case Hit.MISS:
            return (MarkDebility("unprepared"), Note("You are Out of Supply."))


def _establish_false_identity(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (AddLasting("false_identity_2"),)
        case Hit.WEAK:
            return (AddLasting("false_identity_1"),)
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _augur(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    guide = (AddLasting("augur"),) if details.upgraded else ()
    match hit:
        case Hit.STRONG:
            return (Momentum(2), *guide)
        case Hit.WEAK:
            return (Momentum(1), *guide)
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _awaken_simulacrum(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    life = SetAssetMeter("awakening", "health")
    match hit:
        case Hit.STRONG:
            return (life, AddLasting("simulacrum"))
        case Hit.WEAK:
            return (life, AddLasting("simulacrum_wild"))
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _bind(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    if hit is Hit.MISS:
        return (PAY_THE_PRICE,)
    options = [
        _option(f"{animal} pelt: +1 {stat}", AddLasting("pelt", stat))
        for stat, animal in _PELTS.items()
    ]
    if details.upgraded:
        # Bind's second ability: a beast's pelt, for +2 with the stat you name.
        options += [
            _option(f"Beast pelt: +2 {stat}", AddLasting("beast_pelt", stat)) for stat in _STATS
        ]
    choose = Choose(tuple(options))
    if hit is Hit.WEAK:
        return (FollowUp("endure_stress", 2), choose)
    return (choose,)


def _scry(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    observe = Note("You may Gather Information through observation using +shadow or +wits.")
    match hit:
        case Hit.STRONG:
            return (observe,)
        case Hit.WEAK:
            return (
                Choose(
                    (
                        _option("Your blood: Endure Harm (2 harm)", FollowUp("endure_harm", 2)),
                        _option(
                            "Something precious: Endure Stress (2 stress)",
                            FollowUp("endure_stress", 2),
                        ),
                        _option("Provisions: -2 supply", MeterChange("supply", -2)),
                    )
                ),
                observe,
            )
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _shadow_walk(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Momentum(1), AddLasting("shadow_walk"))
        case Hit.WEAK:
            return (
                Note(
                    "The shadows try to lead you astray. You must first Face Danger to find "
                    "your way."
                ),
                Momentum(1),
                AddLasting("shadow_walk"),
            )
        case Hit.MISS:
            return (PAY_THE_PRICE,)


def _sway(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    whisper = AddLasting("sway_upgraded" if details.upgraded else "sway")
    return _ritual((whisper,), (FollowUp("endure_stress", 1),))(hit, details)


def _ward(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    if hit is Hit.MISS:
        return (PAY_THE_PRICE,)
    # Ward's second ability improves each effect: +2 momentum, +2 harm, and almost certain.
    momentum, odds = ("+2", "almost certain") if details.upgraded else ("+1", "likely")
    options = (
        _option(
            "Crossing",
            Note(f"When a foe first crosses the boundary, take {momentum} momentum with /adjust."),
        ),
        _option("Harm", AddLasting("ward_harm_2" if details.upgraded else "ward_harm")),
        _option(
            "Trap",
            Note(f"Your ward is {odds} to trap a foe within the boundary: /ask {odds}."),
        ),
    )
    count = 2 if hit is Hit.STRONG else 1
    return (Choose(options, count=count, minimum=count),)


ASSET_MOVE_OUTCOMES: dict[str, OutcomeRule] = {
    "craft_arrow": _craft_arrow,
    "carve_rune": _ritual((AddLasting("carved_rune"),), (FollowUp("endure_stress", 2),)),
    "create_elixir": _create_elixir,
    "commemorate": _commemorate,
    "scrape_by": _scrape_by,
    "establish_false_identity": _establish_false_identity,
    "augur": _augur,
    "awaken_simulacrum": _awaken_simulacrum,
    "bind": _bind,
    "commune": _ritual((AddLasting("commune"),), (FollowUp("endure_stress", 1),)),
    "cast_runes": _ritual((AddLasting("runes"),), (Momentum(-2),)),
    "invoke": _ritual(
        (AssetMeterFromActionDie("invoke", "essence"),), (FollowUp("endure_stress", 2),)
    ),
    "keen": _upgraded_ritual(
        (AddLasting("keen"),), (AddLasting("keen_once"),), (FollowUp("endure_stress", 2),)
    ),
    "draw_blood_rune": _ritual((AddLasting("blood_rune"),), (AssetDebility("leech", on=True),)),
    "capture_light": lambda hit, details: (
        (PAY_THE_PRICE,)
        if hit is Hit.MISS
        else (SetAssetMeter("lightbearer", "light", 6 if hit is Hit.STRONG else 3),)
    ),
    "scry": _scry,
    "shadow_walk": _shadow_walk,
    "sway": _sway,
    "fashion_talisman": lambda hit, details: {
        Hit.STRONG: (AddLasting("talisman_2"),),
        Hit.WEAK: (AddLasting("talisman_1"),),
        Hit.MISS: (PAY_THE_PRICE,),
    }[hit],
    "tether": _ritual((Note("You are tethered to this place."),), (FollowUp("endure_stress", 2),)),
    "focus_totem": _ritual((AddLasting("totem"),), (FollowUp("endure_stress", 1),)),
    "paint_visage": _upgraded_ritual(
        (AddLasting("visage"),), (AddLasting("visage_attack"),), (FollowUp("endure_harm", 2),)
    ),
    "ward": _ward,
}

OUTCOMES: dict[str, OutcomeRule] = {
    "face_danger": _face_danger,
    "secure_an_advantage": _secure_an_advantage,
    "aid_your_ally": _aid_your_ally,
    "gather_information": _gather_information,
    "heal": _heal,
    "resupply": _resupply,
    "make_camp": _make_camp,
    "undertake_a_journey": _undertake_a_journey,
    "reach_your_destination": _reach_your_destination,
    "compel": _compel,
    "sojourn": _sojourn,
    "draw_the_circle": _draw_the_circle,
    "forge_a_bond": _forge_a_bond,
    "test_your_bond": _test_your_bond,
    "swear_an_iron_vow": _swear_an_iron_vow,
    "fulfill_your_vow": _fulfill_your_vow,
    "enter_the_fray": _enter_the_fray,
    "strike": _strike,
    "clash": _clash,
    "battle": _battle,
    "write_your_epilogue": _write_your_epilogue,
    "end_the_fight": _end_the_fight,
    "endure_harm": _endure("health", "Embrace the pain"),
    "endure_stress": _endure("spirit", "Embrace the darkness"),
    "face_death": _face_death,
    "face_desolation": _face_desolation,
    "companion_endure_harm": _companion_endure_harm,
    **ASSET_MOVE_OUTCOMES,
}


DEFAULT_DETAILS = MoveDetails()


def outcome(move: str, hit: Hit, details: MoveDetails = DEFAULT_DETAILS) -> tuple[Effect, ...]:
    """Return the effects of a move's result.

    Args:
        move: The move id.
        hit: The result.
        details: Facts about the move being made that change its outcome.

    Returns:
        The effects, in the order to apply them.

    Raises:
        KeyError: If the table has no entry for the move.
    """
    return OUTCOMES[move](hit, details)
