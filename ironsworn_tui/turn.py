"""One chat message, from text to applied outcome, with no UI code.

The TUI drives a [`TurnEngine`][ironsworn_tui.turn.TurnEngine] in this order:

1. [`suggest`][ironsworn_tui.turn.TurnEngine.suggest] sends the message to the decision model
   and returns what the suggestion bar offers.
2. [`make_move`][ironsworn_tui.turn.TurnEngine.make_move] rolls the move the player confirmed
   and returns the roll card.
3. [`burn`][ironsworn_tui.turn.TurnEngine.burn] optionally burns momentum on the card.
4. [`resolve`][ironsworn_tui.turn.TurnEngine.resolve] applies the card's effects with the
   player's choices, saves, and returns the follow-up moves the result calls for.
5. Each follow-up, in order, goes to
   [`roll_follow_up`][ironsworn_tui.turn.TurnEngine.roll_follow_up] for the follow-ups that
   roll, [`pay_the_price`][ironsworn_tui.turn.TurnEngine.pay_the_price], or
   [`forsake`][ironsworn_tui.turn.TurnEngine.forsake]. No new move can be made while one
   is owed. [`endure`][ironsworn_tui.turn.TurnEngine.endure] doesn't make a follow-up: it
   adds an owed Endure Harm or Endure Stress, for the `/endure` command.

In the TUI, the decision call runs in a worker: the TUI calls
[`log_message`][ironsworn_tui.turn.TurnEngine.log_message], then
[`decide`][ironsworn_tui.turn.TurnEngine.decide] in the worker, then
[`accept`][ironsworn_tui.turn.TurnEngine.accept] on the UI thread. `suggest` does all three
at once. The player's next move, or [`no_move`][ironsworn_tui.turn.TurnEngine.no_move],
saves the message as a jevtester case. [`skip`][ironsworn_tui.turn.TurnEngine.skip] leaves
it unsaved.

The owed follow-ups, the next move's add, Turn the Tide, and the End the Fight offer are
saved in the campaign, so they survive a restart. A rolled card that isn't resolved isn't,
and neither is a message waiting for a move: its case is lost.
"""

import dataclasses
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from ironsworn_tui.abilities import (
    ABILITIES,
    LASTING,
    AvailableBoost,
    Boost,
    BoostRef,
    RollFacts,
    adjust_outcome,
    boost_effects,
    boosted_harm,
    entry_boosts,
    final_hit,
)
from ironsworn_tui.assets import change_asset_meter, discard, set_debility
from ironsworn_tui.campaign import (
    CONDITION_FOR,
    Campaign,
    Debility,
    Foe,
    Lasting,
    Meter,
    OwedMove,
    ProgressTrack,
    meter_max,
)
from ironsworn_tui.cases import CaseSink, build_case, case_id, play_suite_name
from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import DecideError, Decision, JsonObject, TurnState, build_request
from ironsworn_tui.moves import (
    AID_YOUR_ALLY,
    AIDED_MOVE,
    ATTACK,
    CANNOT_TELL,
    NO_MOVE,
    Context,
    attack_move,
    context_options,
)
from ironsworn_tui.outcomes import (
    AddLasting,
    AddToNextMove,
    AssetDebility,
    AssetMeterChange,
    AssetMeterFromActionDie,
    AssetMeterFromRank,
    Choose,
    ClearDebility,
    CompanionHealth,
    CompleteVow,
    DiscardAsset,
    Effect,
    EndJourney,
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
    MoveDetails,
    Note,
    Option,
    RaiseStat,
    Recommit,
    RemoveTarget,
    RollTable,
    SetAssetMeter,
    SetInitiative,
    outcome,
)
from ironsworn_tui.policy import Suggestion, Thresholds, suggest
from ironsworn_tui.rules.action import ActionRoll, burn_momentum, evaluate_action
from ironsworn_tui.rules.datasworn import Datasworn, Stat, StatOption, plain_text
from ironsworn_tui.rules.dice import Hit, roll_challenge_dice
from ironsworn_tui.rules.oracles import (
    Likelihood,
    OracleResult,
    YesNo,
    ask_yes_no,
    roll_oracle,
)
from ironsworn_tui.rules.progress import (
    TICKS_PER_BOX,
    TRACK_TICKS,
    ProgressRoll,
    Rank,
    evaluate_progress,
    roll_progress,
)
from ironsworn_tui.rules.suffer import Endurance, evaluate_endure_harm, evaluate_endure_stress

PAY_THE_PRICE_TABLE = "classic/fate/pay_the_price/pay_the_price"
TIDE_ADD = 1
PROGRESS_MOVES = {
    "reach_your_destination",
    "fulfill_your_vow",
    "end_the_fight",
    "write_your_epilogue",
}
ATTACKS = {"strike", "clash"}
# The meter a Masked character's mask is tied to, by material.
MASK_TRACKS: dict[str, Meter] = {
    "thunderwood": "health",
    "bloodwood": "health",
    "ghostwood": "spirit",
    "whisperwood": "spirit",
}
# What a move costs before it's rolled, apart from any boost.
PRE_ROLL: dict[str, tuple[Effect, ...]] = {"create_elixir": (MeterChange("supply", -1),)}
# The rolled follow-ups, and what each rolls with when no boost changes it.
ROLLED_FOLLOW_UPS: dict[str, Stat | None] = {
    "endure_harm": None,
    "endure_stress": None,
    "companion_endure_harm": None,
    "face_death": "heart",
    "face_desolation": "heart",
    "scrape_by": "wits",
}
# Endure table results that call for Face Death or Face Desolation without a condition.
FATAL_RESULTS = {
    "The harm is mortal.": "face_death",
    "You are overwhelmed.": "face_desolation",
}
FATE_DEBILITIES: dict[str, tuple[Debility, Debility]] = {
    "endure_harm": ("wounded", "maimed"),
    "endure_stress": ("shaken", "corrupted"),
}


class TurnError(Exception):
    """The move can't be made now, such as an attack outside a fight."""


class Decider(Protocol):
    """Anything that answers a decide request, such as a `JevtesterClient`."""

    def decide(self, request: JsonObject, target: str) -> Decision:
        """Send a request to a target and return its answers."""
        ...


@dataclass(frozen=True)
class MoveInputs:
    """What the player tells the app before some moves.

    Attributes:
        vow: The new vow's name for Swear an Iron Vow, or the vow for Fulfill Your Vow and
            Forsake Your Vow. Defaults to the only active vow.
        rank: The rank of a new vow or journey.
        foes: Each foe's name and rank, for Enter the Fray and Draw the Circle.
        destination: The destination of a new journey, for Undertake a Journey.
        heal_self: For Heal, True when the character mends their own wounds.
        amount: How much of an asset meter to spend, for Lightbearer's unleashed light.
        companion: For Heal, the companion asset being healed.
    """

    vow: str | None = None
    rank: Rank | None = None
    foes: tuple[tuple[str, Rank], ...] = ()
    destination: str | None = None
    heal_self: bool = True
    amount: int | None = None
    companion: str | None = None


NO_INPUTS = MoveInputs()


@dataclass(frozen=True)
class RollCard:
    """A move's roll and the effects its result will apply.

    Attributes:
        move: The move id, after `attack` resolves to Strike or Clash.
        name: The move name.
        rolled_with: What the roll used, such as "iron", "supply", or "progress".
        action: The action roll, for an action-roll move.
        progress: The progress roll, for a progress move.
        effects: The effects [`resolve`][ironsworn_tui.turn.TurnEngine.resolve] applies.
            Options a marked condition blocks are left out.
        outcome_text: The result's text from the move data, with links shown as move names.
        hit: The result, after any boost that counts one result as another.
        tide: True when Turn the Tide was armed for this move.
        boosts: The labels of the boosts the player turned on.
        burn_available: True when burning momentum would improve the dice's result.
        can_reroll: True when a boost lets the player reroll dice now.
        can_late_add: True when a boost lets the player add after rolling.
    """

    move: str
    name: str
    rolled_with: str
    action: ActionRoll | None
    progress: ProgressRoll | None
    effects: tuple[Effect, ...]
    outcome_text: str
    hit: Hit
    tide: bool = False
    boosts: tuple[str, ...] = ()
    burn_available: bool = False
    can_reroll: bool = False
    can_late_add: bool = False


@dataclass
class _Pending:
    card: RollCard
    details: MoveDetails
    vow: ProgressTrack | None
    endurance: Endurance | None = None
    boosts: tuple[AvailableBoost, ...] = ()
    value: int = 0
    adds: int = 0
    rerolled: bool = False
    late: bool = False
    burned: bool = False
    automatic: bool = False
    companion: str | None = None
    lasting: list[Lasting] = dataclasses.field(default_factory=list[Lasting])


class TurnEngine:
    """Runs turns against a campaign: suggestions, rolls, outcomes, and follow-ups.

    The engine never decides a rules question for the player: a choice in an outcome comes
    back to the player through [`resolve`][ironsworn_tui.turn.TurnEngine.resolve].
    """

    def __init__(
        self,
        campaign: Campaign,
        data: Datasworn,
        rng: random.Random,
        thresholds: Thresholds,
        decider: Decider | None = None,
        target: str = "decision-1@foundry",
        path: Path | None = None,
        style: CriteriaStyle = CriteriaStyle.GUIDE,
        cases: CaseSink | None = None,
    ) -> None:
        """Create an engine.

        Args:
            campaign: The campaign the turns change.
            data: The Datasworn data.
            rng: The source of every die roll.
            thresholds: The policy thresholds for the target.
            decider: Answers decide requests. Without one, every message gets the full list.
            target: The jevtester target to ask.
            path: Where to save the campaign after each turn, or None to not save.
            style: How the `move` question describes each move.
            cases: Where to save each answered turn as a jevtester case, or None to not save.
        """
        self.campaign = campaign
        self.data = data
        self.rng = rng
        self.thresholds = thresholds
        self.decider = decider
        self.target = target
        self.path = path
        self.style = style
        self.cases = cases
        unknown = [lasting.kind for lasting in campaign.lasting if lasting.kind not in LASTING]
        if unknown:
            raise ValueError(f"unknown lasting effects: {', '.join(unknown)}")
        self._pending: _Pending | None = None
        self._initiative_set = False
        self._harm = 0
        self._companion: str | None = None
        self._action_die = 0
        self._answering: tuple[Context, Decision] | None = None

    @property
    def card(self) -> RollCard | None:
        """The roll card waiting for the player's choices, if any."""
        return self._pending.card if self._pending else None

    @property
    def follow_ups(self) -> tuple[OwedMove, ...]:
        """The follow-up moves still owed, in order."""
        return tuple(self.campaign.follow_ups)

    def suggest(self, text: str) -> Suggestion:
        """Log a message and ask the decision model which move it triggers.

        A failed request gives a suggestion with the full move list, and logs why.
        """
        self.log_message(text)
        suggestion = self.decide(text)
        if suggestion.note is not None:
            self.campaign.add_log("note", suggestion.note)
        self.accept(suggestion)
        return suggestion

    def accept(self, suggestion: Suggestion) -> None:
        """Remember the decision the player's next move answers, so it can be saved as a case.

        The TUI calls this when a worker's answer reaches the screen. A failed request is
        never saved.
        """
        decision = suggestion.decision
        if decision is not None and decision.move is not None:
            self._answering = (self.campaign.context, decision)
        else:
            self._answering = None

    def no_move(self) -> None:
        """Answer the last message with no move, and save that as its case if the model
        answered it."""
        self._record(NO_MOVE, None)
        self.campaign.add_log("outcome", "No move")
        self.save()

    def skip(self) -> None:
        """Leave the last message without a move, and don't save it as a case."""
        self._answering = None

    def _record(self, option: str, stat: Stat | None) -> None:
        """Save the waiting decision as a case labeled with what the player did.

        Nothing is saved when no decision is waiting, when the move isn't an option in the
        context the message was asked in (because the context changed since), or when the
        engine uses criteria other than the guide criteria the play suites ask with.
        """
        answering, self._answering = self._answering, None
        if answering is None or self.cases is None:
            return
        context, decision = answering
        if self.style is not CriteriaStyle.GUIDE:
            return
        if option not in context_options(context):
            self.campaign.add_log("note", f"Case not saved: {option} wasn't offered then")
            return
        name = self.campaign.character.name
        case = build_case(self.data, decision, option, stat, case_id(name))
        try:
            self.cases.add_case(play_suite_name(context), case)
        except DecideError as error:
            self.campaign.add_log("note", f"Case not saved: {error}")

    def log_message(self, text: str) -> None:
        """Log and save a player message."""
        self.campaign.add_log("message", text)
        self.save()

    def decide(self, text: str) -> Suggestion:
        """Ask the decision model which move a message triggers, without changing the campaign.

        The TUI calls this from a worker thread, so it reads the campaign and writes nothing.
        A failed request gives a suggestion with the full move list and a note saying why.
        """
        campaign = self.campaign
        character = campaign.character
        state = TurnState(
            name=character.name,
            character=f"{character.name}, {character.description}",
            situation=self._situation(),
            context=campaign.context,
            initiative=campaign.initiative if campaign.foes else None,
            player_says=text,
        )
        decision: Decision | None = None
        note: str | None = None
        if self.decider is not None:
            request = build_request(self.data, state, self.style)
            try:
                decision = self.decider.decide(request, self.target)
            except DecideError as error:
                note = f"No suggestion: {error}"
            else:
                if decision.move is None:
                    note = f"No suggestion: {decision.error}"
        result = suggest(decision, campaign.context, self.thresholds)
        if result.band == "escalate":
            result = dataclasses.replace(result, options=result.options + self.asset_options())
        return dataclasses.replace(result, note=note)

    def _situation(self) -> str:
        campaign = self.campaign
        parts = [campaign.situation] if campaign.situation else []
        if campaign.foes:
            parts.append("Foes: " + ", ".join(foe.name for foe in campaign.foes) + ".")
        if campaign.journey is not None:
            parts.append(f"Journey: {campaign.journey.name}.")
        return " ".join(parts)

    def full_list(self) -> Suggestion:
        """Return a suggestion that offers every move in the context, then Aid Your Ally and
        the asset moves, with none selected."""
        result = suggest(None, self.campaign.context, self.thresholds)
        extra = (AID_YOUR_ALLY, *self.asset_options())
        return dataclasses.replace(result, options=result.options + extra)

    def inputs_needed(self, option: str) -> tuple[str, ...]:
        """Return the fields the player must fill in before a move, such as `vow` and `rank`.

        Fields: `vow`, `rank`, `foes`, `destination`, and `treat` (for Heal: yourself or
        someone else).
        """
        campaign = self.campaign
        match option:
            case "swear_an_iron_vow":
                return ("vow", "rank")
            case "enter_the_fray" | "draw_the_circle":
                return ("foes",)
            case "undertake_a_journey" if campaign.journey is None:
                return ("destination", "rank")
            case "heal":
                return ("treat",)
            case "fulfill_your_vow" | "forsake_your_vow" if len(campaign.vows) > 1:
                return ("vow",)
            case _:
                return ()

    def set_scene(self, text: str) -> None:
        """Replace the situation text."""
        self.campaign.situation = text
        self.campaign.add_log("command", f"Scene: {text}")
        self.save()

    def set_target(self, name: str) -> None:
        """Select the foe an attack targets.

        Raises:
            TurnError: If no foe in the fight has the name.
        """
        if name not in {foe.name for foe in self.campaign.foes}:
            raise TurnError(f"No foe named {name!r} in the fight")
        self.campaign.target = name
        self.campaign.add_log("command", f"Target: {name}")
        self.save()

    def end_fight(self, how: str) -> None:
        """End the fight without End the Fight, as when it's lost, fled, or settled by Battle.

        Args:
            how: What happened, for the log.
        """
        self.campaign.end_fight()
        self.campaign.add_log("command", f"The fight ends: {how}")
        self.save()

    def arm_tide(self) -> None:
        """Arm Turn the Tide for the next move.

        Raises:
            TurnError: Outside a fight, when the character has initiative, or when it was used.
        """
        campaign = self.campaign
        if not campaign.foes or campaign.initiative != "foe":
            raise TurnError("Turn the Tide needs a fight where the foe has initiative")
        if campaign.tide_used:
            raise TurnError("Turn the Tide was already used in this fight")
        campaign.tide_armed = True
        campaign.add_log("command", "Turn the Tide is armed")
        self.save()

    def disarm_tide(self) -> None:
        """Disarm Turn the Tide without using it."""
        self.campaign.tide_armed = False
        self.campaign.add_log("command", "Turn the Tide is disarmed")
        self.save()

    def boosts_for(self, option: str) -> tuple[AvailableBoost, ...]:
        """Return the boosts the player can turn on for a move, in asset and ability order.

        Args:
            option: A `move` option, or a follow-up move such as `endure_harm`.
        """
        move = self._move_for(option)
        found = [*self._owned_boosts(), *self._lasting_boosts()]
        return tuple(a for a in found if self._why_not(a, move) is None)

    def _move_for(self, option: str) -> str:
        if option != ATTACK:
            return option
        campaign = self.campaign
        return attack_move(
            "character" if campaign.tide_armed else campaign.initiative or "character"
        )

    def _owned_boosts(self) -> list[AvailableBoost]:
        found: list[AvailableBoost] = []
        for owned in self.campaign.character.assets:
            asset = self.data.asset(owned.id)
            for number, marked in enumerate(owned.marked, 1):
                if not marked:
                    continue
                for variant, boost in enumerate(entry_boosts(ABILITIES[(owned.id, number)])):
                    found.append(
                        AvailableBoost(BoostRef(owned.id, number, variant), asset.name, boost)
                    )
        return found

    def _why_not(self, available: AvailableBoost, move: str) -> str | None:
        """Return why a boost doesn't apply to a move now, or None when it does."""
        boost, ref = available.boost, available.ref
        campaign = self.campaign
        label = available.label
        rolls_as = {move, AIDED_MOVE} if move == AID_YOUR_ALLY else {move}
        if boost.moves is not None and not rolls_as & set(boost.moves):
            names = ", ".join(self.move_name(m) for m in boost.moves)
            return f"{label} is for {names}"
        if move in PROGRESS_MOVES and _only_changes_the_action_roll(boost):
            return f"{label} needs an action roll"
        if ref.lasting is not None:
            return None
        owned = campaign.character.asset(ref.asset)
        needed = boost.needs_asset
        if needed is not None and campaign.character.asset_or_none(needed) is None:
            return f"{label} needs {self.data.asset(needed).name}"
        if any(not owned.marked[number - 1] for number in boost.needs):
            return f"{label} needs ability {', '.join(map(str, boost.needs))} marked"
        if boost.limit == "fight" and _use_key(ref) in campaign.fight_uses:
            return f"{label} was already used once per fight"
        if boost.limit == "one_time" and ref.ability in owned.spent:
            return f"{label} was already used, one time only"
        if boost.tide and not campaign.tide_armed:
            return f"{label} needs Turn the Tide"
        if boost.field is not None:
            name, choice = boost.field
            if owned.fields.get(name) != choice:
                select = self.data.asset(ref.asset).selects[name]
                return f"{label} needs {select.choices[choice].label}"
        return None

    def move_name(self, move: str) -> str:
        """Return a core or asset move's name."""
        return self.data.find_move(move).name

    def companions(self) -> dict[str, str]:
        """The character's companions, by lowercase name, id, and given name, to asset id."""
        found: dict[str, str] = {}
        for companion in self._companions():
            owned = self.campaign.character.asset(companion)
            found[companion] = companion
            found[self.data.asset(companion).name.lower()] = companion
            if "name" in owned.fields:
                found[owned.fields["name"].lower()] = companion
        return found

    def asset_options(self) -> tuple[str, ...]:
        """Return the moves the character's marked asset abilities add, such as a ritual's."""
        options: list[str] = []
        for owned in self.campaign.character.assets:
            asset = self.data.asset(owned.id)
            for ability, marked in zip(asset.abilities, owned.marked, strict=True):
                if marked:
                    options += [move.id for move in ability.moves]
        return tuple(options)

    def _lasting_boosts(self) -> list[AvailableBoost]:
        found: list[AvailableBoost] = []
        for index, lasting in enumerate(self.campaign.lasting):
            boost = LASTING[lasting.kind].boost
            if lasting.stat is not None:
                boost = dataclasses.replace(
                    boost, label=f"{boost.label} ({lasting.stat})", only_stat=lasting.stat
                )
            found.append(AvailableBoost(BoostRef("", 0, lasting=index), "", boost))
        return found

    def _check_boosts(self, move: str, refs: Sequence[BoostRef]) -> tuple[AvailableBoost, ...]:
        """Return the boosts the player turned on, or raise if one can't be used."""
        character = self.campaign.character
        chosen: list[AvailableBoost] = []
        lasting = self._lasting_boosts()
        for ref in refs:
            if ref.lasting is not None:
                if not 0 <= ref.lasting < len(lasting):
                    raise TurnError(f"there's no lasting effect {ref.lasting + 1}")
                available = lasting[ref.lasting]
                reason = self._why_not(available, move)
                if reason is not None:
                    raise TurnError(reason)
                chosen.append(available)
                continue
            owned = character.asset_or_none(ref.asset)
            if owned is None:
                raise TurnError(f"{character.name} doesn't own {ref.asset}")
            asset = self.data.asset(ref.asset)
            if not 1 <= ref.ability <= len(owned.marked) or not owned.marked[ref.ability - 1]:
                raise TurnError(f"{asset.name}'s ability {ref.ability} isn't marked")
            boosts = entry_boosts(ABILITIES[(ref.asset, ref.ability)])
            if not 0 <= ref.variant < len(boosts):
                raise TurnError(f"{asset.name} {ref.ability} has no variant {ref.variant + 1}")
            available = AvailableBoost(ref, asset.name, boosts[ref.variant])
            reason = self._why_not(available, move)
            if reason is not None:
                raise TurnError(reason)
            chosen.append(available)
        abilities = [(a.ref.asset, a.ref.ability, a.ref.lasting) for a in chosen]
        kinds = [
            (self.campaign.lasting[a.ref.lasting].kind, self.campaign.lasting[a.ref.lasting].stat)
            for a in chosen
            if a.ref.lasting is not None
        ]
        if len(set(kinds)) != len(kinds):
            raise TurnError("turn on one of each kind of lasting effect")
        if len(set(abilities)) != len(abilities):
            raise TurnError("turn on one variant of each ability")
        if sum(a.boost.roll is not None for a in chosen) > 1:
            raise TurnError("only one boost can change what the move rolls")
        return tuple(chosen)

    def _boost_value(self, available: AvailableBoost) -> tuple[str, int]:
        """Return what a boost makes the move roll, and its value."""
        roll = available.boost.roll
        assert roll is not None
        character = self.campaign.character
        owned = character.asset(available.ref.asset)
        match roll.kind:
            case "stat":
                stat = _stat(roll.name)
                return stat, character.stats.value(stat)
            case "meter":
                return roll.name, owned.meters[roll.name]
            case "field":
                stat = self._field_stat(available, roll.name)
                return stat, character.stats.value(stat)
            case "condition":
                meter = _meter(roll.name)
                return meter, character.meter(meter)

    def _field_stat(self, available: AvailableBoost, field: str) -> Stat:
        owned = self.campaign.character.asset(available.ref.asset)
        choice = owned.fields.get(field)
        if choice is None:
            raise TurnError(
                f"set {available.asset_name}'s {field} first, with /asset set "
                f"{available.ref.asset} {field} <choice>"
            )
        stat = self.data.asset(available.ref.asset).selects[field].choices[choice].stat
        assert stat is not None
        return stat

    def _unleash(
        self, boosts: tuple[AvailableBoost, ...], inputs: MoveInputs
    ) -> tuple[AvailableBoost, ...]:
        """Turn Lightbearer's unleashed light into a cost and a harm, from the amount."""
        changed: list[AvailableBoost] = []
        for available in boosts:
            meter = available.boost.unleash
            if meter is None:
                changed.append(available)
                continue
            have = self.campaign.character.asset(available.ref.asset).meters[meter]
            if inputs.amount is None or not 1 <= inputs.amount <= have:
                raise TurnError(f"choose how much {meter} to unleash, from 1 to {have}")
            boost = dataclasses.replace(
                available.boost,
                before=(AssetMeterChange(available.ref.asset, meter, -inputs.amount),),
                set_harm=1 + inputs.amount,
            )
            changed.append(dataclasses.replace(available, boost=boost))
        return tuple(changed)

    def _use(self, boosts: tuple[AvailableBoost, ...]) -> None:
        """Record limited boosts as used, end lasting effects used up, and pay what the boosts
        cost before rolling."""
        campaign = self.campaign
        used_up = [
            campaign.lasting[a.ref.lasting]
            for a in boosts
            if a.ref.lasting is not None
            and LASTING[campaign.lasting[a.ref.lasting].kind].expires == "use"
        ]
        for available in boosts:
            ref, boost = available.ref, available.boost
            if ref.lasting is not None:
                self._apply(boost.before, [], None)
                continue
            if boost.limit == "fight":
                campaign.fight_uses.append(_use_key(ref))
            elif boost.limit == "one_time":
                campaign.character.asset(ref.asset).spent.append(ref.ability)
            self._apply(boost.before, [], None)
        for lasting in used_up:
            self._end_lasting(lasting)

    def make_move(
        self,
        option: str,
        stat: Stat | None = None,
        adds: int = 0,
        inputs: MoveInputs = NO_INPUTS,
        boosts: Sequence[BoostRef] = (),
    ) -> RollCard | None:
        """Make a move and roll it.

        Every check happens before the campaign changes, so a refused move changes nothing.

        Args:
            option: A `move` option for the context, or `end_the_fight` when the last result
                offered it.
            stat: The stat, for a move with a stat question. A boost that changes what the
                move rolls replaces it.
            adds: The player's add, beyond the boosts'.
            inputs: What the move needs to know first, such as a new vow's name and rank.
            boosts: The asset boosts the player turned on. See
                [`boosts_for`][ironsworn_tui.turn.TurnEngine.boosts_for].

        Returns:
            The roll card, or None for Forsake Your Vow, which has no roll and applies at once.

        Raises:
            TurnError: If the move can't be made now, a stat or input it needs is missing, or
                a boost can't be used.
        """
        campaign = self.campaign
        if self._pending is not None:
            raise TurnError("Resolve the current roll card first")
        if campaign.follow_ups:
            owed = self.move_name(campaign.follow_ups[0].move)
            raise TurnError(f"Make the owed {owed} first")
        if option in (NO_MOVE, CANNOT_TELL):
            raise TurnError(f"{option} makes no move")
        if option == "end_the_fight":
            # End the Fight isn't a `move` option, so it can't label a case.
            chosen = self._check_boosts(option, boosts)
            self._answering = None
            return self._end_the_fight(chosen)
        if option not in (*context_options(campaign.context), AID_YOUR_ALLY, *self.asset_options()):
            name = "Attack" if option == ATTACK else self.move_name(option)
            raise TurnError(f"{name} isn't a move in the {campaign.context} context")
        if option == "forsake_your_vow":
            vow = self._vow(inputs)
            self._record(option, None)
            self._forsake(vow)
            return None
        tide = campaign.tide_armed
        move = self._move_for(option)
        self._check_inputs(move, inputs)
        chosen = self._unleash(self._check_boosts(move, boosts), inputs)
        automatic = any(a.boost.automatic for a in chosen)
        value: tuple[str, int] | None = None
        if move not in PROGRESS_MOVES and not automatic:
            rolling = [a for a in chosen if a.boost.roll is not None]
            value = self._boost_value(rolling[0]) if rolling else self._value(move, stat, inputs)
            self._check_stat_fields(chosen, value[0])
        if move == "fulfill_your_vow":
            self._vow(inputs)
        boost_adds = self._boost_adds(chosen)

        self._record(option, stat)
        campaign.end_fight_offered = False
        if not campaign.foes:
            # A once-per-fight use outside a fight counts only for a fight this move starts.
            campaign.fight_uses = []
        if tide:
            campaign.initiative = "character"
            campaign.tide_used = True
            campaign.tide_armed = False
        used = self._lasting_of(chosen)
        self._use(chosen)
        self._apply(PRE_ROLL.get(move, ()), [], None)
        vow = self._set_up(move, inputs)
        details = self._details(inputs, move)
        pending = _Pending(
            card=_EMPTY_CARD,
            details=details,
            vow=vow,
            boosts=chosen,
            automatic=automatic,
            companion=inputs.companion,
            lasting=used,
        )
        if automatic:
            card = self._card(move, "automatic", None, None, pending)
        elif value is None:
            card = self._progress_card(move, vow, pending)
        else:
            pending.value = value[1]
            pending.adds = adds + boost_adds + campaign.next_add + (TIDE_ADD if tide else 0)
            campaign.next_add = 0
            roll = self._roll(pending.value, pending.adds)
            card = self._card(move, value[0], roll, None, pending)
        pending.card = dataclasses.replace(card, tide=tide)
        self._pending = pending
        campaign.add_log("roll", _describe(pending.card))
        return pending.card

    def _boost_adds(self, chosen: tuple[AvailableBoost, ...]) -> int:
        """The boosts' adds, reading any asset meter they add before its cost is paid."""
        character = self.campaign.character
        return sum(a.boost.add for a in chosen) + sum(
            character.asset(a.ref.asset).meters[a.boost.add_meter]
            for a in chosen
            if a.boost.add_meter is not None
        )

    def _check_stat_fields(self, chosen: tuple[AvailableBoost, ...], rolled_with: str) -> None:
        for available in chosen:
            only = available.boost.only_stat
            if only is not None and rolled_with != only:
                raise TurnError(f"{available.label} applies to {only} rolls")
            field = available.boost.stat_field
            if field is None:
                continue
            stat = self._field_stat(available, field)
            if rolled_with != stat:
                raise TurnError(f"{available.label} applies to {stat} rolls")

    def _details(self, inputs: MoveInputs = NO_INPUTS, move: str = "") -> MoveDetails:
        upgraded = False
        if move in self.data.asset_moves:
            upgraded = self.campaign.character.has_ability(self.data.asset_for_move(move), 2)
        return MoveDetails(
            heal_self=inputs.heal_self and inputs.companion is None,
            harm=self.campaign.character.harm,
            foe_harm=self._foe_harm(),
            upgraded=upgraded,
        )

    def _vow(self, inputs: MoveInputs) -> ProgressTrack:
        vows = self.campaign.vows
        if inputs.vow is not None:
            try:
                return self.campaign.vow(inputs.vow)
            except KeyError as error:
                raise TurnError(str(error)) from error
        if len(vows) == 1:
            return vows[0]
        raise TurnError("name the vow")

    def _check_inputs(self, move: str, inputs: MoveInputs) -> None:
        campaign = self.campaign
        match move:
            case "swear_an_iron_vow":
                if inputs.vow is None or inputs.rank is None:
                    raise TurnError("Swear an Iron Vow needs the vow and its rank")
                if inputs.vow in {vow.name for vow in campaign.vows}:
                    raise TurnError(f"there's already a vow named {inputs.vow!r}")
            case "enter_the_fray" | "draw_the_circle":
                names = [name for name, _ in inputs.foes] + [foe.name for foe in campaign.foes]
                if not inputs.foes:
                    raise TurnError(f"{move} needs each foe's name and rank")
                if len(set(names)) != len(names):
                    raise TurnError("give each foe a different name")
            case "undertake_a_journey" if campaign.journey is None:
                if inputs.destination is None or inputs.rank is None:
                    raise TurnError("a new journey needs a destination and a rank")
            case "heal" if (
                inputs.companion is not None and inputs.companion not in self._companions()
            ):
                raise TurnError(f"{inputs.companion} isn't a companion you have")
            case "resupply" if "unprepared" in campaign.character.debilities:
                raise TurnError("you can't Resupply while unprepared")
            case "reach_your_destination" if campaign.journey is None:
                raise TurnError("there's no journey")
            case _:
                pass

    def _set_up(self, move: str, inputs: MoveInputs) -> ProgressTrack | None:
        campaign = self.campaign
        match move:
            case "swear_an_iron_vow":
                assert inputs.vow is not None and inputs.rank is not None
                vow = ProgressTrack(name=inputs.vow, rank=inputs.rank)
                campaign.vows.append(vow)
                return vow
            case "fulfill_your_vow":
                return self._vow(inputs)
            case "enter_the_fray" | "draw_the_circle":
                campaign.foes.extend(Foe(name=name, rank=rank) for name, rank in inputs.foes)
                campaign.target = campaign.target or campaign.foes[0].name
                campaign.initiative = campaign.initiative or "character"
            case "undertake_a_journey" if campaign.journey is None:
                assert inputs.destination is not None and inputs.rank is not None
                campaign.journey = ProgressTrack(name=inputs.destination, rank=inputs.rank)
            case _:
                pass
        return None

    def _value(self, move: str, stat: Stat | None, inputs: MoveInputs) -> tuple[str, int]:
        character = self.campaign.character
        if move == "make_camp":
            return "supply", character.supply
        if move == "heal" and inputs.heal_self:
            lower: Stat = "iron" if character.stats.iron < character.stats.wits else "wits"
            return lower, character.stats.value(lower)
        rolls_as = AIDED_MOVE if move == AID_YOUR_ALLY else move
        conditions = self.data.find_move(rolls_as).trigger.conditions
        stats: list[Stat] = []
        for condition in conditions:
            if condition.method != "player_choice":
                continue
            for option in condition.roll_options:
                if isinstance(option, StatOption) and option.stat not in stats:
                    stats.append(option.stat)
        if len(stats) == 1:
            return stats[0], character.stats.value(stats[0])
        if stat is None or stat not in stats:
            name = self.move_name(move)
            raise TurnError(f"{name} needs one of these stats: {', '.join(stats)}")
        return stat, character.stats.value(stat)

    def _roll(self, value: int, adds: int) -> ActionRoll:
        action_die = self.rng.randint(1, 6)
        dice = roll_challenge_dice(self.rng)
        return evaluate_action(value, adds, self.campaign.character.momentum, action_die, dice)

    def _progress_card(self, move: str, vow: ProgressTrack | None, pending: _Pending) -> RollCard:
        campaign = self.campaign
        if move == "write_your_epilogue":
            ticks, rolled_with = campaign.bonds, "bonds"
        elif move == "reach_your_destination":
            if campaign.journey is None:
                raise TurnError("there's no journey")
            ticks, rolled_with = campaign.journey.ticks, "progress"
        elif move == "end_the_fight":
            foe = campaign.target_foe()
            if foe is None:
                raise TurnError("there's no foe")
            ticks, rolled_with = foe.ticks, "progress"
        else:
            if vow is None:
                raise TurnError(f"{move} needs a vow")
            ticks, rolled_with = vow.ticks, "progress"
        return self._card(move, rolled_with, None, roll_progress(ticks, self.rng), pending)

    def _card(
        self,
        move: str,
        rolled_with: str,
        action: ActionRoll | None,
        progress: ProgressRoll | None,
        pending: _Pending,
    ) -> RollCard:
        """Build the roll card for a roll, with the boosts' effects on the result."""
        boosts = [a.boost for a in pending.boosts]
        if action is not None:
            dice_hit, match = action.hit, action.match
        elif progress is not None:
            dice_hit, match = progress.hit, progress.match
        elif pending.automatic:
            dice_hit, match = Hit.STRONG, False
        else:
            raise TurnError(f"{move} has no roll")
        hit = final_hit(dice_hit, boosts)
        harm = boosted_harm(pending.details.harm, hit, boosts, burned=pending.burned)
        details = dataclasses.replace(pending.details, harm=harm)
        move_data = self.data.find_move(move)
        text = ""
        if move_data.outcomes is not None:
            outcomes = move_data.outcomes
            text = {
                Hit.STRONG: outcomes.strong_hit,
                Hit.WEAK: outcomes.weak_hit,
                Hit.MISS: outcomes.miss,
            }[hit].text
        elif move == AID_YOUR_ALLY:
            aided = self.data.move(AIDED_MOVE).outcomes
            text = move_data.text if hit is not Hit.MISS or aided is None else aided.miss.text
        effects = adjust_outcome(outcome(move, hit, details), boosts, hit)
        if move == "heal" and pending.companion is not None and hit is not Hit.MISS:
            effects = (CompanionHealth(2, every=False), *effects)
        if move == "companion_endure_harm" and pending.companion is not None:
            effects += self._companion_death(pending.companion, hit, action)
        facts = RollFacts(
            hit=hit,
            match=match,
            action_die=action.action_die if action is not None else None,
            rolled_with=rolled_with,
            burned=pending.burned,
            rerolled=pending.rerolled,
            late=pending.late,
        )
        for boost in boosts:
            for_ally = move == AID_YOUR_ALLY and boost.moves is not None and move not in boost.moves
            effects += boost_effects(boost, facts, for_ally=for_ally)
        effects = self._allowed(effects)
        endurance = pending.endurance
        if endurance is not None and hit is Hit.MISS and endurance.meter_after == 0:
            effects = (*effects, self._fate_choice(move, endurance))
        fresh = not (pending.burned or pending.rerolled)
        return RollCard(
            move=move,
            name=move_data.name,
            rolled_with=rolled_with,
            action=action,
            progress=progress,
            effects=effects,
            outcome_text=plain_text(text),
            hit=hit,
            boosts=tuple(a.label for a in pending.boosts),
            burn_available=self._burn_available(action, progress, pending),
            can_reroll=fresh and _reroll_allowed(boosts, hit),
            can_late_add=(
                action is not None
                and not pending.late
                and not pending.burned
                and any(b.late_add for b in boosts)
            ),
        )

    def _burn_available(
        self, action: ActionRoll | None, progress: ProgressRoll | None, pending: _Pending
    ) -> bool:
        if action is not None:
            return action.burn_available
        if progress is None or pending.burned:
            return False
        if not any(a.boost.burn_progress for a in pending.boosts):
            return False
        return _burn_one_die(progress, self.campaign.character.momentum).hit > progress.hit

    def _allowed(self, effects: tuple[Effect, ...]) -> tuple[Effect, ...]:
        """Leave out options that raise a meter whose condition is marked (rulebook page 37)."""
        debilities = self.campaign.character.debilities

        def blocked(option: Option) -> bool:
            cleared = {e.debility for e in option.effects if isinstance(e, ClearDebility)}
            return any(
                isinstance(e, MeterChange)
                and e.amount > 0
                and CONDITION_FOR[e.meter] in debilities
                and CONDITION_FOR[e.meter] not in cleared
                for e in option.effects
            )

        allowed: list[Effect] = []
        for effect in effects:
            if isinstance(effect, Choose):
                options = tuple(option for option in effect.options if not blocked(option))
                if options:
                    minimum = min(effect.minimum, len(options))
                    allowed.append(dataclasses.replace(effect, options=options, minimum=minimum))
            else:
                allowed.append(effect)
        return tuple(allowed)

    def _fate_choice(self, move: str, endurance: Endurance) -> Choose:
        unmarked: list[Debility] = [
            debility
            for debility in FATE_DEBILITIES[move]
            if debility not in self.campaign.character.debilities
        ]
        options = [Option(label=f"Mark {d}", effects=(MarkDebility(d),)) for d in unmarked]
        options.append(
            Option(label="Roll on the table", effects=(RollTable(endurance.fate_table_id),))
        )
        return Choose(tuple(options))

    def _foe_harm(self) -> int:
        foe = self.campaign.target_foe()
        return foe.harm if foe is not None else 1

    def burn(self) -> RollCard:
        """Burn momentum on the roll card, and reset momentum.

        On an action roll, each challenge die below the momentum is cancelled. With a boost
        that allows it, as Revenant's does, a progress roll can cancel one die.

        Raises:
            TurnError: If there's no card, or burning wouldn't improve its result.
        """
        pending = self._pending
        if pending is None or not pending.card.burn_available:
            raise TurnError("burning momentum wouldn't improve this roll")
        card = pending.card
        character = self.campaign.character
        before = card.hit
        action, progress = card.action, card.progress
        if action is not None:
            action = burn_momentum(action)
            if pending.endurance is not None:
                pending.endurance = dataclasses.replace(pending.endurance, roll=action)
        else:
            assert progress is not None
            progress = _burn_one_die(progress, character.momentum)
        character.reset_momentum()
        pending.burned = True
        new_card = self._card(card.move, card.rolled_with, action, progress, pending)
        if before is Hit.MISS and new_card.hit is Hit.WEAK:
            new_card = self._burn_initiative(pending, new_card)
        pending.card = dataclasses.replace(new_card, tide=card.tide)
        self.campaign.add_log("roll", f"Burned momentum: {pending.card.hit.label}")
        return pending.card

    def _burn_initiative(self, pending: _Pending, card: RollCard) -> RollCard:
        """Veteran: take initiative, once per fight, when burning turns a miss to a weak hit."""
        campaign = self.campaign
        for available in pending.boosts:
            key = _use_key(available.ref) + ":initiative"
            if available.boost.burn_initiative and campaign.foes and key not in campaign.fight_uses:
                campaign.fight_uses.append(key)
                return dataclasses.replace(
                    card, effects=(*card.effects, SetInitiative("character"))
                )
        return card

    def reroll(self, dice: Sequence[int]) -> RollCard:
        """Reroll some of the card's dice, as a boost allows.

        Args:
            dice: The dice to reroll: 0 for the action die, 1 and 2 for the challenge dice.

        Raises:
            TurnError: If no boost allows a reroll now, or the dice aren't valid.
        """
        pending = self._pending
        if pending is None or not pending.card.can_reroll:
            raise TurnError("no boost allows a reroll now")
        card = pending.card
        boosts = [a.boost for a in pending.boosts]
        picked = set(dice)
        if not picked or not picked <= {0, 1, 2} or len(picked) != len(dice):
            raise TurnError(
                "pick dice to reroll: 0 for the action die, 1 and 2 for the challenge dice"
            )
        if 0 in picked and card.action is None:
            raise TurnError("a progress roll has no action die")
        only_one = not any(
            b.reroll is not None and b.reroll != "one_challenge_on_miss" for b in boosts
        )
        if only_one and (0 in picked or len(picked) != 1):
            raise TurnError("reroll one challenge die")
        action, progress = card.action, card.progress
        if action is not None:
            die = self.rng.randint(1, 6) if 0 in picked else action.action_die
            first, second = action.challenge_dice
        else:
            assert progress is not None
            die = 0
            first, second = progress.challenge_dice
        first = self.rng.randint(1, 10) if 1 in picked else first
        second = self.rng.randint(1, 10) if 2 in picked else second
        if action is not None:
            pending.adds += max((b.reroll_add for b in boosts), default=0)
            action = evaluate_action(
                pending.value, pending.adds, action.momentum, die, (first, second)
            )
            if pending.endurance is not None:
                pending.endurance = dataclasses.replace(pending.endurance, roll=action)
        else:
            assert progress is not None
            progress = evaluate_progress(progress.ticks, (first, second))
        pending.rerolled = True
        new_card = self._card(card.move, card.rolled_with, action, progress, pending)
        pending.card = dataclasses.replace(new_card, tide=card.tide)
        self.campaign.add_log("roll", f"Rerolled: {_describe(pending.card)}")
        return pending.card

    def late_add(self) -> RollCard:
        """Take a boost's add after rolling, as Improviser's and Wright's allow, and its cost.

        Raises:
            TurnError: If no boost allows it now.
        """
        pending = self._pending
        if pending is None or not pending.card.can_late_add:
            raise TurnError("no boost allows an add after rolling now")
        card = pending.card
        action = card.action
        assert action is not None
        pending.adds += sum(a.boost.late_add for a in pending.boosts)
        pending.late = True
        action = evaluate_action(
            pending.value, pending.adds, action.momentum, action.action_die, action.challenge_dice
        )
        new_card = self._card(card.move, card.rolled_with, action, None, pending)
        pending.card = dataclasses.replace(new_card, tide=card.tide)
        self.campaign.add_log("roll", f"Added after rolling: {_describe(pending.card)}")
        return pending.card

    def resolve(self, choices: Sequence[Sequence[int]] = ()) -> tuple[OwedMove, ...]:
        """Apply the roll card's effects, and save.

        Unless the move says otherwise, a strong hit in a fight takes initiative, and a weak hit
        or miss loses it (rulebook page 53). That includes suffer moves.

        Args:
            choices: For each choice on the card, in order, the indices of the options the
                player picked.

        Returns:
            The follow-up moves still owed, in order.

        Raises:
            TurnError: If there's no card, or the choices don't fit the card. The card stays
                pending, and nothing is applied.
        """
        pending = self._pending
        if pending is None:
            raise TurnError("there's no roll card")
        card = pending.card
        self._check_choices(card.effects, list(choices))
        campaign = self.campaign
        owed_before = len(campaign.follow_ups)
        self._initiative_set = False
        boosts = [a.boost for a in pending.boosts]
        self._harm = boosted_harm(pending.details.harm, card.hit, boosts, burned=pending.burned)
        self._companion = pending.companion
        self._action_die = card.action.action_die if card.action is not None else 0
        self._apply(card.effects, list(choices), pending.vow)
        self._expire_lasting(pending)
        hit = card.hit
        if card.tide:
            queued = campaign.follow_ups[owed_before:]
            if hit is Hit.MISS:
                if not any(owed.move == "pay_the_price" for owed in queued):
                    campaign.follow_ups.append(OwedMove(move="pay_the_price"))
                campaign.add_log("note", "Turn the Tide failed: suffer a dire outcome.")
            else:
                self._momentum(1)
        if campaign.foes and not self._initiative_set:
            campaign.initiative = "character" if hit is Hit.STRONG else "foe"
        foe = campaign.target_foe()
        campaign.end_fight_offered = (
            card.move in ATTACKS
            and hit is Hit.STRONG
            and foe is not None
            and foe.ticks >= TICKS_PER_BOX
        )
        self._pending = None
        self.save()
        return self.follow_ups

    def _check_choices(self, effects: tuple[Effect, ...], choices: list[Sequence[int]]) -> None:
        """Raise if the choices don't fit the card, before anything is applied."""

        def walk(effects: tuple[Effect, ...]) -> None:
            for effect in effects:
                if not isinstance(effect, Choose):
                    continue
                if not choices:
                    raise TurnError("the card needs a choice")
                picked = choices.pop(0)
                if not effect.minimum <= len(picked) <= effect.count:
                    raise TurnError(f"choose {effect.minimum} to {effect.count}")
                if len(set(picked)) != len(picked):
                    raise TurnError("choose each option once")
                for index in picked:
                    if not 0 <= index < len(effect.options):
                        raise TurnError(f"there's no option {index + 1}")
                    walk(effect.options[index].effects)

        walk(effects)
        if choices:
            raise TurnError("more choices than the card has")

    def _apply(
        self, effects: tuple[Effect, ...], choices: list[Sequence[int]], vow: ProgressTrack | None
    ) -> None:
        for effect in effects:
            self._apply_one(effect, choices, vow)

    def _apply_one(
        self, effect: Effect, choices: list[Sequence[int]], vow: ProgressTrack | None
    ) -> None:
        campaign = self.campaign
        character = campaign.character
        match effect:
            case Choose(options=options):
                for index in choices.pop(0):
                    chosen = options[index]
                    campaign.add_log("outcome", chosen.label)
                    self._apply(chosen.effects, choices, vow)
            case Momentum(amount=amount):
                self._momentum(amount)
            case MeterChange(meter=meter, amount=amount):
                self._meter(meter, amount)
            case MarkProgress(track=track, times=times):
                self._mark(track, times, vow)
            case SetInitiative(who=who):
                if campaign.foes:
                    campaign.initiative = who
                    self._initiative_set = True
            case FollowUp(move=move, amount=amount, asset=asset):
                vow_name = vow.name if move == "forsake_your_vow" and vow is not None else None
                campaign.follow_ups.append(
                    OwedMove(move=move, amount=amount, vow=vow_name, asset=asset)
                )
            case ClearDebility(debility=debility):
                character.clear_debility(debility)
            case MarkDebility(debility=debility):
                character.mark_debility(debility)
                campaign.add_log("outcome", f"Marked {debility}")
            case RollTable(table_id=table_id):
                result = roll_oracle(self.data, table_id, self.rng)
                text = plain_text(result.text)
                campaign.add_log("outcome", f"{result.roll}: {text}")
                for start, move in FATAL_RESULTS.items():
                    if text.startswith(start):
                        campaign.follow_ups.append(OwedMove(move=move))
            case AddToNextMove(amount=amount):
                campaign.next_add += amount
            case MarkExperience(less=less):
                if vow is not None:
                    character.experience += max(0, int(vow.rank) - less)
            case CompleteVow():
                if vow is not None and vow in campaign.vows:
                    campaign.vows.remove(vow)
            case Recommit(track=track):
                target = vow if track == "vow" else campaign.journey
                if target is not None:
                    target.recommit()
            case EndJourney():
                campaign.journey = None
            case RemoveTarget():
                foe = campaign.target_foe()
                if foe is not None:
                    campaign.remove_foe(foe)
            case Note(text=text):
                campaign.add_log("note", text)
            case InflictHarm(amount=amount):
                foe = campaign.target_foe()
                if foe is not None:
                    foe.mark(amount if amount is not None else self._harm)
            case AssetMeterChange(asset=asset, meter=meter, amount=amount):
                if character.asset_or_none(asset) is not None:
                    change_asset_meter(character, self.data, asset, meter, amount)
            case AssetMeterFromRank(asset=asset, meter=meter):
                if vow is not None and character.asset_or_none(asset) is not None:
                    change_asset_meter(character, self.data, asset, meter, int(vow.rank))
            case GainExperience(amount=amount):
                character.experience += amount
            case ExperiencePerAbility(asset=asset, amount=amount):
                owned = character.asset_or_none(asset)
                if owned is not None:
                    character.experience += amount * sum(owned.marked)
            case MomentumFromMeter(meter=meter, asset=asset):
                if asset is None:
                    self._momentum(character.meter(_meter(meter)))
                elif character.asset_or_none(asset) is not None:
                    self._momentum(character.asset(asset).meters[meter])
            case AssetDebility(asset=asset, on=on):
                if character.asset_or_none(asset) is not None:
                    set_debility(character, asset, on=on)
            case RaiseStat(stat=stat):
                setattr(character.stats, stat, min(5, character.stats.value(stat) + 1))
                campaign.add_log("outcome", f"Raised {stat} to {character.stats.value(stat)}")
            case DiscardAsset(asset=asset):
                if character.asset_or_none(asset) is not None:
                    discard(character, asset)
                    campaign.add_log("outcome", f"Discarded {self.data.asset(asset).name}")
            case MaxSpirit(amount=amount):
                character.spirit_max = max(0, min(5, character.spirit_max + amount))
                character.spirit = min(character.spirit, character.spirit_max)
            case AddLasting(kind=kind, stat=stat):
                campaign.lasting.append(Lasting(kind=kind, stat=stat))
                campaign.add_log(
                    "outcome", f"Lasting: {_lasting_label(Lasting(kind=kind, stat=stat))}"
                )
            case SetAssetMeter(asset=asset, meter=meter, value=value):
                owned = character.asset_or_none(asset)
                if owned is not None:
                    top = meter_max(self.data, owned, meter)
                    owned.meters[meter] = top if value is None else min(top, value)
            case AssetMeterFromActionDie(asset=asset, meter=meter):
                if character.asset_or_none(asset) is not None:
                    change_asset_meter(character, self.data, asset, meter, self._action_die)
            case CompanionHealth(amount=amount, every=every):
                companions = self._companions() if every else [self._companion]
                for companion in companions:
                    if companion is not None and character.asset_or_none(companion) is not None:
                        change_asset_meter(character, self.data, companion, "health", amount)
            case InflictRolledHarm():
                foe = campaign.target_foe()
                roll = self.rng.randint(1, 6)
                campaign.add_log("outcome", f"Extra harm: {roll}")
                if foe is not None:
                    foe.mark(roll)
            case MaskTrack(amount=amount):
                masked = character.asset_or_none("masked")
                material = masked.fields.get("material") if masked is not None else None
                if material is not None:
                    self._meter(MASK_TRACKS[material], amount)

    def _momentum(self, amount: int) -> None:
        setback = self.campaign.character.change_momentum(amount)
        if setback:
            self.campaign.add_log("note", _setback_note(setback))

    def _meter(self, meter: Meter, amount: int) -> None:
        character = self.campaign.character
        before = character.meter(meter)
        character.change_meter(meter, amount)
        if meter != "supply" or amount >= 0:
            return
        excess = -amount - before
        if before > 0 and character.supply == 0 and character.has_ability("outcast", 1):
            # Outcast: "suffer any remaining -supply as -momentum", then Scrape By.
            if excess > 0:
                self._momentum(-excess)
            self.campaign.follow_ups.append(OwedMove(move="scrape_by"))
            return
        if before > 0 and character.supply == 0:
            character.mark_debility("unprepared")
            self.campaign.add_log("outcome", "Out of Supply: marked unprepared")
        if excess > 0 and "unprepared" in character.debilities:
            self.campaign.add_log(
                "note",
                f"Out of Supply: exchange {excess} supply for health, spirit, or momentum.",
            )

    def _mark(self, track: str, times: int, vow: ProgressTrack | None) -> None:
        campaign = self.campaign
        if track == "vow" and vow is not None:
            vow.mark(times)
        elif track == "journey" and campaign.journey is not None:
            campaign.journey.mark(times)
        elif track == "target":
            foe = campaign.target_foe()
            if foe is not None:
                foe.mark(times)
        elif track == "bonds":
            boxes = campaign.bonds // TICKS_PER_BOX
            campaign.bonds = min(TRACK_TICKS, campaign.bonds + times)
            filled = campaign.bonds // TICKS_PER_BOX - boxes
            if filled and campaign.character.has_ability("bonded", 2):
                # Bonded: "take 1 experience and +2 momentum" for each box filled.
                campaign.character.experience += filled
                self._momentum(2 * filled)
                campaign.add_log("outcome", "Bonded: a bonds box filled, +1 experience")

    def _forsake(self, vow: ProgressTrack) -> None:
        self.campaign.vows.remove(vow)
        self.campaign.add_log("outcome", f"Forsook the vow: {vow.name}")
        self.campaign.follow_ups.append(OwedMove(move="endure_stress", amount=int(vow.rank)))
        self.save()

    def forsake(self) -> tuple[OwedMove, ...]:
        """Make the next follow-up, Forsake Your Vow: clear the vow, then owe Endure Stress.

        Returns:
            The follow-up moves still owed.

        Raises:
            TurnError: If the next follow-up isn't Forsake Your Vow.
        """
        owed = self._next_follow_up({"forsake_your_vow"})
        vow = self._vow(MoveInputs(vow=owed.vow))
        self._forsake(vow)
        return self.follow_ups

    def _next_follow_up(self, moves: set[str]) -> OwedMove:
        if self._pending is not None:
            raise TurnError("resolve the current roll card first")
        follow_ups = self.campaign.follow_ups
        if not follow_ups or follow_ups[0].move not in moves:
            raise TurnError(f"the next follow-up isn't {' or '.join(sorted(moves))}")
        return follow_ups.pop(0)

    def _end_the_fight(self, chosen: tuple[AvailableBoost, ...]) -> RollCard:
        campaign = self.campaign
        if not campaign.end_fight_offered:
            raise TurnError("End the Fight needs a strong hit on a Strike or Clash first")
        campaign.end_fight_offered = False
        self._use(chosen)
        pending = _Pending(card=_EMPTY_CARD, details=self._details(), vow=None, boosts=chosen)
        pending.card = self._progress_card("end_the_fight", None, pending)
        self._pending = pending
        campaign.add_log("roll", _describe(pending.card))
        return pending.card

    def roll_follow_up(self, boosts: Sequence[BoostRef] = ()) -> RollCard | None:
        """Make the next follow-up that rolls, and roll it.

        These are Endure Harm, Endure Stress, Companion Endure Harm, Face Death, Face
        Desolation, and Scrape By. For the three endure moves the damage applies at once,
        before the roll. On a miss at 0, Endure Harm and Endure Stress offer marking each
        unmarked debility of the pair, or rolling on the move's table.

        Args:
            boosts: The asset boosts the player turned on.

        Returns:
            The roll card, or None when a boost replaces the move, as a Shield-Bearer's
            sacrificed shield does.

        Raises:
            TurnError: If the next follow-up doesn't roll, or a boost can't be used.
        """
        follow_ups = self.campaign.follow_ups
        character = self.campaign.character
        if (
            self._pending is not None
            or not follow_ups
            or follow_ups[0].move not in ROLLED_FOLLOW_UPS
        ):
            self._next_follow_up(set(ROLLED_FOLLOW_UPS))
        move = follow_ups[0].move
        companion: str | None = None
        if move == "companion_endure_harm":
            companion = self._owed_companion(follow_ups[0])
            if companion is None:
                gone = follow_ups.pop(0)
                self.campaign.add_log(
                    "note", f"No Companion Endure Harm: {gone.asset} is no longer with you"
                )
                self.save()
                return None
        chosen = self._check_boosts(move, boosts)
        override: tuple[str, int] | None = None
        rolling = [a for a in chosen if a.boost.roll is not None]
        if rolling:
            override = self._boost_value(rolling[0])
        stat = ROLLED_FOLLOW_UPS[move] or ("iron" if move == "endure_harm" else "heart")
        self._check_stat_fields(chosen, override[0] if override else stat)
        adds = self._boost_adds(chosen)
        owed = self._next_follow_up(set(ROLLED_FOLLOW_UPS))
        used = self._lasting_of(chosen)
        self._use(chosen)
        skipping = [a for a in chosen if a.boost.skip]
        if skipping:
            self.campaign.add_log("outcome", f"{skipping[0].label}: no {self.move_name(owed.move)}")
            for available in chosen:
                self._apply(available.boost.after, [], None)
            self.save()
            return None
        pending = _Pending(
            card=_EMPTY_CARD,
            details=MoveDetails(),
            vow=None,
            boosts=chosen,
            adds=adds,
            lasting=used,
        )
        if any(a.boost.automatic for a in chosen):
            pending.automatic = True
            pending.card = self._card(owed.move, "automatic", None, None, pending)
            self._pending = pending
            self.campaign.add_log("roll", _describe(pending.card))
            return pending.card
        action_die = self.rng.randint(1, 6)
        dice = roll_challenge_dice(self.rng)
        if owed.move in FATE_DEBILITIES:
            amount = owed.amount if owed.amount is not None else self._foe_harm()
            endurance = self._endure(owed.move, amount, action_die, dice, adds)
            rolled_with, value = endurance.stat, endurance.roll.value
            if override is not None:
                rolled_with, value = override
                roll = evaluate_action(value, adds, endurance.momentum_after, action_die, dice)
                endurance = dataclasses.replace(endurance, roll=roll)
            pending.details = MoveDetails(meter_above_zero=endurance.meter_after > 0)
            pending.endurance = endurance
            roll = endurance.roll
            lost = f" ({amount} {endurance.meter} lost first)"
        elif owed.move == "companion_endure_harm":
            assert companion is not None
            amount = owed.amount if owed.amount is not None else self._foe_harm()
            rolled_with, value, lost = self._companion_damage(companion, amount)
            if override is not None:
                rolled_with, value = override
            pending.companion = companion
            roll = evaluate_action(value, adds, character.momentum, action_die, dice)
        else:
            rolled_with, value = override or (stat, character.stats.value(_stat(stat)))
            roll = evaluate_action(value, adds, character.momentum, action_die, dice)
            lost = ""
        pending.value = value
        card = self._card(owed.move, rolled_with, roll, None, pending)
        pending.card = card
        self._pending = pending
        self.campaign.add_log("roll", _describe(card) + lost)
        return card

    def _endure(
        self, move: str, amount: int, action_die: int, dice: tuple[int, int], adds: int
    ) -> Endurance:
        character = self.campaign.character
        if move == "endure_harm":
            endurance = evaluate_endure_harm(
                character.health,
                character.stats.iron,
                amount,
                character.momentum,
                action_die,
                dice,
                adds,
            )
            character.health = endurance.meter_after
        else:
            endurance = evaluate_endure_stress(
                character.spirit,
                character.stats.heart,
                amount,
                character.momentum,
                action_die,
                dice,
                adds,
            )
            character.spirit = endurance.meter_after
        character.momentum = endurance.momentum_after
        if endurance.setback:
            self.campaign.add_log("note", _setback_note(endurance.setback))
        return endurance

    def _owed_companion(self, owed: OwedMove) -> str | None:
        """Return the companion an owed Companion Endure Harm is for, or None when the
        character no longer has it, as after it died or was discarded."""
        if owed.asset is not None:
            if self.campaign.character.asset_or_none(owed.asset) is None:
                return None
            return owed.asset
        companions = self._companions()
        if len(companions) != 1:
            raise TurnError("name the companion with /asset harm <companion> <harm>")
        return companions[0]

    def _companions(self) -> list[str]:
        """The companion assets the character owns."""
        return [
            owned.id
            for owned in self.campaign.character.assets
            if self.data.asset(owned.id).category == "Companion"
        ]

    def _companion_damage(self, companion: str, amount: int) -> tuple[str, int, str]:
        """Take the harm off the companion's health, and any left over off momentum.

        Returns:
            What the roll uses (heart or the companion's health, whichever is higher), its
            value, and a note for the log.
        """
        character = self.campaign.character
        owned = character.asset(companion)
        health = owned.meters["health"]
        absorbed = min(health, amount)
        owned.meters["health"] = health - absorbed
        if amount > absorbed:
            self._momentum(-(amount - absorbed))
        after = owned.meters["health"]
        name = self.data.asset(companion).name
        if after >= character.stats.heart:
            return f"{name}'s health", after, f" ({amount} harm to {name} first)"
        return "heart", character.stats.heart, f" ({amount} harm to {name} first)"

    def _companion_death(
        self, companion: str, hit: Hit, action: ActionRoll | None
    ) -> tuple[Effect, ...]:
        """On a miss with a 1 on the action die at 0 health, the companion dies."""
        owned = self.campaign.character.asset_or_none(companion)
        if owned is None or hit is not Hit.MISS or action is None or action.action_die != 1:
            return ()
        if owned.meters["health"] != 0:
            return ()
        name = self.data.asset(companion).name
        return (
            Note(f"{name} is dead."),
            ExperiencePerAbility(companion, 1),
            DiscardAsset(companion),
        )

    def _lasting_of(self, chosen: tuple[AvailableBoost, ...]) -> list[Lasting]:
        """The lasting effects among the chosen boosts."""
        lasting = self.campaign.lasting
        return [lasting[a.ref.lasting] for a in chosen if a.ref.lasting is not None]

    def _end_lasting(self, lasting: Lasting) -> None:
        campaign = self.campaign
        if lasting in campaign.lasting:
            campaign.lasting.remove(lasting)
            campaign.add_log("outcome", f"Ended: {_lasting_label(lasting)}")

    def end_lasting(self, index: int) -> None:
        """End a lasting effect by hand.

        Args:
            index: Its index in the campaign's list.

        Raises:
            TurnError: If there's no such effect.
        """
        if not 0 <= index < len(self.campaign.lasting):
            raise TurnError(f"there's no lasting effect {index + 1}")
        self._end_lasting(self.campaign.lasting[index])
        self.save()

    def take_trophy(self, use: Literal["ritual", "sojourn"]) -> None:
        """Slayer's third ability: take a trophy from a slain beast or horror.

        Raises:
            TurnError: Without Slayer's third ability.
        """
        if not self.campaign.character.has_ability("slayer", 3):
            raise TurnError("taking a trophy needs Slayer's third ability")
        self._apply((AddLasting(f"trophy_{use}"),), [], None)
        self.save()

    def browse_archive(self) -> None:
        """Lorekeeper's third ability, one time only: raise wits by 1 and roll an action die.

        On 1 to 3, the character must also mark corrupted or Face Desolation, ignoring
        momentum. The log says so, and the player chooses.

        Raises:
            TurnError: Without the ability, or when it was already used.
        """
        character = self.campaign.character
        if not character.has_ability("lorekeeper", 3):
            raise TurnError("browsing the archive needs Lorekeeper's third ability")
        owned = character.asset("lorekeeper")
        if 3 in owned.spent:
            raise TurnError("the archive's forbidden depths can be browsed one time only")
        owned.spent.append(3)
        character.stats.wits = min(5, character.stats.wits + 1)
        roll = self.rng.randint(1, 6)
        line = f"Browsed the forbidden depths: wits is now {character.stats.wits}, rolled {roll}"
        if roll <= 3:
            line += (
                ". Mark corrupted (/adjust corrupted mark) or Face Desolation, ignoring momentum."
            )
        self.campaign.add_log("outcome", line)
        self.save()

    def endure(self, move: Literal["endure_harm", "endure_stress"], amount: int) -> None:
        """Owe Endure Harm or Endure Stress, for harm or stress the player applies from the
        fiction, such as Pay the Price's or a foe's attack.

        Raises:
            TurnError: If the amount isn't at least 1.
        """
        if amount < 1:
            raise TurnError("the harm or stress must be at least 1")
        self.campaign.follow_ups.append(OwedMove(move=move, amount=amount))
        what = "harm" if move == "endure_harm" else "stress"
        self.campaign.add_log("command", f"{self.campaign.character.name} faces {amount} {what}")
        self.save()

    def decline_end_fight(self) -> None:
        """Pass on the End the Fight offer, so the fight goes on."""
        self.campaign.end_fight_offered = False
        self.save()

    def harm_companion(self, companion: str, amount: int) -> None:
        """Owe Companion Endure Harm for a companion.

        Raises:
            TurnError: If the asset isn't a companion the character owns.
        """
        if companion not in self._companions():
            raise TurnError(f"{companion} isn't a companion {self.campaign.character.name} has")
        self.campaign.follow_ups.append(
            OwedMove(move="companion_endure_harm", amount=amount, asset=companion)
        )
        self.campaign.add_log("command", f"{self.data.asset(companion).name} faces {amount} harm")
        self.save()

    def lasting_labels(self) -> tuple[str, ...]:
        """The lasting effects' names, in order."""
        return tuple(_lasting_label(lasting) for lasting in self.campaign.lasting)

    def _expire_lasting(self, pending: _Pending) -> None:
        """End the lasting effects the resolved roll used up."""
        campaign = self.campaign
        card = pending.card
        spent: list[Lasting] = []
        if card.action is not None and card.action.action_die == 1:
            spent += [
                lasting for lasting in pending.lasting if LASTING[lasting.kind].expires == "one"
            ]
        groups = {LASTING[lasting.kind].group for lasting in spent} - {None}
        spent += [lasting for lasting in campaign.lasting if LASTING[lasting.kind].group in groups]
        for lasting in spent:
            self._end_lasting(lasting)
        self.expire_low()

    def expire_low(self) -> None:
        """End the lasting effects that last only while health, spirit, and momentum are
        above 0, such as an elixir, if one of them isn't."""
        campaign = self.campaign
        character = campaign.character
        if min(character.health, character.spirit, character.momentum) < 1:
            low = [each for each in campaign.lasting if LASTING[each.kind].expires == "low"]
            for lasting in low:
                self._end_lasting(lasting)

    def mark_vow(self, name: str) -> ProgressTrack:
        """Reach a Milestone: mark progress on a vow.

        Fated's third ability gives 1 experience for every two boxes filled on the background
        vow, and a milestone on it ends Fated's debility.

        Raises:
            TurnError: If no active vow has the name.
        """
        campaign = self.campaign
        vow = self._vow(MoveInputs(vow=name))
        boxes = vow.boxes
        vow.mark()
        campaign.add_log("outcome", f"Reach a Milestone: {vow.name} is at {vow.boxes}/10")
        character = campaign.character
        if vow.name == campaign.background_vow:
            if character.has_ability("fated", 3):
                gained = vow.boxes // 2 - boxes // 2
                if gained:
                    character.experience += gained
                    campaign.add_log("outcome", f"Fated: +{gained} experience")
            fated = character.asset_or_none("fated")
            if fated is not None and fated.debility:
                set_debility(character, "fated", on=False)
                campaign.add_log("outcome", "Fated no longer counts as a debility")
            if character.has_ability("fated", 2):
                campaign.add_log("note", "Fated: take +2 momentum or +1 spirit with /adjust.")
        self.save()
        return vow

    def pay_the_price(
        self, method: Literal["obvious", "ask", "table"]
    ) -> OracleResult | YesNo | None:
        """Make the next follow-up, Pay the Price, in one of its three ways.

        Args:
            method: `obvious` makes the most obvious negative outcome happen. `ask` asks the
                yes/no oracle at likely odds whether the player's likelier outcome happens.
                `table` rolls on the Pay the Price table.

        Returns:
            The oracle's answer for `ask`, the table roll for `table`, or None for `obvious`.

        Raises:
            TurnError: If the next follow-up isn't Pay the Price.
        """
        self._next_follow_up({"pay_the_price"})
        result: OracleResult | YesNo | None = None
        if method == "table":
            result = roll_oracle(self.data, PAY_THE_PRICE_TABLE, self.rng)
            self.campaign.add_log(
                "outcome", f"Pay the Price, {result.roll}: {plain_text(result.text)}"
            )
        elif method == "ask":
            result = ask_yes_no(Likelihood.LIKELY, self.rng)
            answer = "yes, the likely outcome" if result.yes else "no, the other outcome"
            self.campaign.add_log(
                "outcome", f"Pay the Price, asked the oracle ({result.roll}): {answer}"
            )
        else:
            self.campaign.add_log("outcome", "Pay the Price: the most obvious negative outcome")
        self.expire_low()
        self.save()
        return result

    def save(self) -> None:
        """Save the campaign, if the engine has a path."""
        if self.path is not None:
            self.campaign.save(self.path)


_EMPTY_CARD = RollCard(
    move="",
    name="",
    rolled_with="",
    action=None,
    progress=None,
    effects=(),
    outcome_text="",
    hit=Hit.MISS,
)


def _only_changes_the_action_roll(boost: Boost) -> bool:
    """True when a boost does nothing but change an action roll: an add, a stat, or a late add."""
    changes_roll = bool(
        boost.add
        or boost.add_meter
        or boost.roll
        or boost.stat_field
        or boost.only_stat
        or boost.late_add
    )
    rest = dataclasses.replace(
        boost,
        add=0,
        add_meter=None,
        roll=None,
        stat_field=None,
        only_stat=None,
        late_add=0,
        late_cost=(),
        before=(),
        on_one=(),
        unleash=None,
        limit=None,
        needs=(),
        tide=False,
        field=None,
    )
    return changes_roll and rest == Boost(boost.label, boost.moves)


def _lasting_label(lasting: Lasting) -> str:
    label = LASTING[lasting.kind].boost.label
    return f"{label} ({lasting.stat})" if lasting.stat is not None else label


def _use_key(ref: BoostRef) -> str:
    return f"{ref.asset}:{ref.ability}"


_STATS: dict[str, Stat] = {
    "edge": "edge",
    "heart": "heart",
    "iron": "iron",
    "shadow": "shadow",
    "wits": "wits",
}
_METERS: dict[str, Meter] = {"health": "health", "spirit": "spirit", "supply": "supply"}


def _stat(name: str) -> Stat:
    return _STATS[name]


def _meter(name: str) -> Meter:
    return _METERS[name]


def _reroll_allowed(boosts: Sequence[Boost], hit: Hit) -> bool:
    """True when a boost allows a reroll after this result."""
    allowed = {
        "any": True,
        "miss": hit is Hit.MISS,
        "weak_or_miss": hit is not Hit.STRONG,
        "one_challenge_on_miss": hit is Hit.MISS,
    }
    return any(boost.reroll is not None and allowed[boost.reroll] for boost in boosts)


def _burn_one_die(progress: ProgressRoll, momentum: int) -> ProgressRoll:
    """Burn momentum on a progress roll to cancel one challenge die below the momentum.

    A cancelled die counts as beaten. The higher die that can be cancelled is.
    """
    first, second = progress.challenge_dice
    score = progress.score
    cancellable = [die for die in (first, second) if die < momentum]
    if not cancellable:
        return progress
    other = second if max(cancellable) == first else first
    beaten = 1 + (score > other)
    hit = {2: Hit.STRONG, 1: Hit.WEAK}[beaten]
    return dataclasses.replace(progress, hit=max(hit, progress.hit))


def _setback_note(setback: int) -> str:
    return (
        f"Face a Setback: exchange {setback} momentum for health, spirit, supply, or progress "
        "on a track."
    )


def _describe(card: RollCard) -> str:
    if card.action is not None:
        roll = card.action
        first, second = roll.challenge_dice
        dice = f"{roll.action_die} + {roll.value} + {roll.adds} = {roll.score} vs {first}, {second}"
        if roll.action_die_cancelled:
            dice += " (action die cancelled)"
        match = roll.match
    elif card.progress is not None:
        progress = card.progress
        first, second = progress.challenge_dice
        dice = f"progress {progress.score} vs {first}, {second}"
        match = progress.match
    else:
        return f"{card.name}: automatic strong hit ({', '.join(card.boosts)})"
    text = f"{card.name} +{card.rolled_with}: {dice}, {card.hit.label}"
    if match:
        text += ", match"
    if card.boosts:
        text += f" ({', '.join(card.boosts)})"
    return text
