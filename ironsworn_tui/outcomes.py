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
        amount: The harm or stress, for Endure Harm and Endure Stress.
    """

    move: str
    amount: int | None = None


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
class Option:
    """One choice on the roll card, with its effects."""

    label: str
    effects: tuple[Effect, ...]


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
    """

    heal_self: bool = True
    harm: int = 2
    foe_harm: int = 1
    meter_above_zero: bool = True


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
    _option("Recuperate: +1 health", MeterChange("health", 1)),
    _option("Partake: -1 supply, +1 health", MeterChange("supply", -1), MeterChange("health", 1)),
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
            return (Choose(_CAMP, count=2),)
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
    _option("Recuperate: +2 health", MeterChange("health", 2)),
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
    "choose one more."
)


def _sojourn(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Choose(_SOJOURN, count=2), _SOJOURN_FOCUS)
        case Hit.WEAK:
            return (Choose(_SOJOURN), _SOJOURN_FOCUS)
        case Hit.MISS:
            return (PAY_THE_PRICE,)


_BOASTS = (
    _option("Grant first strike: your foe has initiative", Momentum(1), SetInitiative("foe")),
    _option("Bare yourself: your foe's harm is +1", Momentum(1), Note("Your foe's harm is +1.")),
    _option("Hold no iron: your harm is 1", Momentum(1), Note("Your harm is 1.")),
    _option("Bloody yourself: Endure Harm (1 harm)", Momentum(1), FollowUp("endure_harm", 1)),
    _option("To the death", Momentum(1), Note("This fight must end with death.")),
)


def _draw_the_circle(hit: Hit, details: MoveDetails) -> tuple[Effect, ...]:
    match hit:
        case Hit.STRONG:
            return (Momentum(1), Choose(_BOASTS, count=2, minimum=0))
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

OUTCOMES: dict[str, OutcomeRule] = {
    "face_danger": _face_danger,
    "secure_an_advantage": _secure_an_advantage,
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
