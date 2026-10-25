"""One chat message, from text to applied outcome, with no UI code.

The TUI drives a [`TurnEngine`][ironsworn_tui.turn.TurnEngine] in this order:

1. [`suggest`][ironsworn_tui.turn.TurnEngine.suggest] sends the message to the decision model
   and returns what the suggestion bar offers.
2. [`make_move`][ironsworn_tui.turn.TurnEngine.make_move] rolls the move the player confirmed
   and returns the roll card.
3. [`burn`][ironsworn_tui.turn.TurnEngine.burn] optionally burns momentum on the card.
4. [`resolve`][ironsworn_tui.turn.TurnEngine.resolve] applies the card's effects with the
   player's choices, saves, and returns the follow-up moves the result calls for.
5. Each follow-up, in order, goes to [`endure`][ironsworn_tui.turn.TurnEngine.endure],
   [`pay_the_price`][ironsworn_tui.turn.TurnEngine.pay_the_price], or
   [`forsake`][ironsworn_tui.turn.TurnEngine.forsake]. No new move can be made while one
   is owed.

The owed follow-ups, the next move's add, Turn the Tide, and the End the Fight offer are
saved in the campaign, so they survive a restart. A rolled card that isn't resolved isn't.
"""

import dataclasses
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from ironsworn_tui.campaign import (
    CONDITION_FOR,
    Campaign,
    Debility,
    Foe,
    Meter,
    OwedMove,
    ProgressTrack,
)
from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import DecideError, Decision, JsonObject, TurnState, build_request
from ironsworn_tui.moves import ATTACK, CANNOT_TELL, NO_MOVE, attack_move, context_options
from ironsworn_tui.outcomes import (
    AddToNextMove,
    Choose,
    ClearDebility,
    CompleteVow,
    Effect,
    EndJourney,
    FollowUp,
    MarkDebility,
    MarkExperience,
    MarkProgress,
    MeterChange,
    Momentum,
    MoveDetails,
    Note,
    Option,
    Recommit,
    RemoveTarget,
    RollTable,
    SetInitiative,
    outcome,
)
from ironsworn_tui.policy import Suggestion, Thresholds, suggest
from ironsworn_tui.rules.action import ActionRoll, burn_momentum, evaluate_action
from ironsworn_tui.rules.datasworn import Datasworn, Stat, StatOption
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
FATE_DEBILITIES: dict[str, tuple[Debility, Debility]] = {
    "endure_harm": ("wounded", "maimed"),
    "endure_stress": ("shaken", "corrupted"),
}
_LINK = re.compile(r"\[([^\]]+)\]\(datasworn:[^)]+\)")


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
    """

    vow: str | None = None
    rank: Rank | None = None
    foes: tuple[tuple[str, Rank], ...] = ()
    destination: str | None = None
    heal_self: bool = True


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
        tide: True when Turn the Tide was armed for this move.
    """

    move: str
    name: str
    rolled_with: str
    action: ActionRoll | None
    progress: ProgressRoll | None
    effects: tuple[Effect, ...]
    outcome_text: str
    tide: bool = False

    @property
    def hit(self) -> Hit:
        """The result."""
        if self.action is not None:
            return self.action.hit
        if self.progress is not None:
            return self.progress.hit
        raise TurnError(f"{self.move} has no roll")

    @property
    def burn_available(self) -> bool:
        """True when burning momentum would improve the result."""
        return self.action is not None and self.action.burn_available


@dataclass
class _Pending:
    card: RollCard
    details: MoveDetails
    vow: ProgressTrack | None
    endurance: Endurance | None = None


def plain_text(text: str) -> str:
    """Show each `datasworn:` link in move text as the move name."""
    return _LINK.sub(r"\1", text)


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
        """
        self.campaign = campaign
        self.data = data
        self.rng = rng
        self.thresholds = thresholds
        self.decider = decider
        self.target = target
        self.path = path
        self.style = style
        self._pending: _Pending | None = None
        self._initiative_set = False

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

        A failed request gives a suggestion with the full move list.
        """
        campaign = self.campaign
        campaign.add_log("message", text)
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
        if self.decider is not None:
            try:
                decision = self.decider.decide(
                    build_request(self.data, state, self.style), self.target
                )
            except DecideError as error:
                campaign.add_log("note", f"No suggestion: {error}")
        return suggest(decision, campaign.context, self.thresholds)

    def _situation(self) -> str:
        campaign = self.campaign
        parts = [campaign.situation] if campaign.situation else []
        if campaign.foes:
            parts.append("Foes: " + ", ".join(foe.name for foe in campaign.foes) + ".")
        if campaign.journey is not None:
            parts.append(f"Journey: {campaign.journey.name}.")
        return " ".join(parts)

    def set_scene(self, text: str) -> None:
        """Replace the situation text."""
        self.campaign.situation = text
        self.campaign.add_log("command", f"Scene: {text}")
        self._save()

    def set_target(self, name: str) -> None:
        """Select the foe an attack targets.

        Raises:
            TurnError: If no foe in the fight has the name.
        """
        if name not in {foe.name for foe in self.campaign.foes}:
            raise TurnError(f"no foe named {name!r} in the fight")
        self.campaign.target = name
        self._save()

    def end_fight(self, how: str) -> None:
        """End the fight without End the Fight, as when it's lost, fled, or settled by Battle.

        Args:
            how: What happened, for the log.
        """
        self.campaign.end_fight()
        self.campaign.add_log("command", f"The fight ends: {how}")
        self._save()

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
        self._save()

    def disarm_tide(self) -> None:
        """Disarm Turn the Tide without using it."""
        self.campaign.tide_armed = False
        self._save()

    def make_move(
        self,
        option: str,
        stat: Stat | None = None,
        adds: int = 0,
        inputs: MoveInputs = NO_INPUTS,
    ) -> RollCard | None:
        """Make a move and roll it.

        Every check happens before the campaign changes, so a refused move changes nothing.

        Args:
            option: A `move` option for the context, or `end_the_fight` when the last result
                offered it.
            stat: The stat, for a move with a stat question.
            adds: The player's add, such as an asset's bonus.
            inputs: What the move needs to know first, such as a new vow's name and rank.

        Returns:
            The roll card, or None for Forsake Your Vow, which has no roll and applies at once.

        Raises:
            TurnError: If the move can't be made now, or a stat or input it needs is missing.
        """
        campaign = self.campaign
        if self._pending is not None:
            raise TurnError("resolve the current roll card first")
        if campaign.follow_ups:
            raise TurnError(f"make the owed {campaign.follow_ups[0].move} first")
        if option in (NO_MOVE, CANNOT_TELL):
            raise TurnError(f"{option} makes no move")
        if option == "end_the_fight":
            return self._end_the_fight()
        if option not in context_options(campaign.context):
            raise TurnError(f"{option} isn't a move in the {campaign.context} context")
        if option == "forsake_your_vow":
            self._forsake(self._vow(inputs))
            return None
        tide = campaign.tide_armed
        move = (
            attack_move("character" if tide else campaign.initiative or "character")
            if option == ATTACK
            else option
        )
        self._check_inputs(move, inputs)
        value: tuple[str, int] | None = None
        if move not in PROGRESS_MOVES:
            value = self._value(move, stat, inputs)
        if move == "fulfill_your_vow":
            self._vow(inputs)

        campaign.end_fight_offered = False
        if tide:
            campaign.initiative = "character"
            campaign.tide_used = True
            campaign.tide_armed = False
        vow = self._set_up(move, inputs)
        details = self._details(inputs)
        if value is None:
            card = self._progress_card(move, vow)
        else:
            roll_adds = adds + campaign.next_add + (TIDE_ADD if tide else 0)
            campaign.next_add = 0
            card = self._card(move, value[0], self._roll(value[1], roll_adds), None, details)
        card = dataclasses.replace(card, tide=tide)
        self._pending = _Pending(card=card, details=details, vow=vow)
        campaign.add_log("roll", _describe(card))
        return card

    def _details(self, inputs: MoveInputs = NO_INPUTS) -> MoveDetails:
        return MoveDetails(
            heal_self=inputs.heal_self,
            harm=self.campaign.character.harm,
            foe_harm=self._foe_harm(),
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
        conditions = self.data.move(move).trigger.conditions
        stats: list[Stat] = [
            option.stat
            for condition in conditions
            if condition.method == "player_choice"
            for option in condition.roll_options
            if isinstance(option, StatOption)
        ]
        if len(stats) == 1:
            return stats[0], character.stats.value(stats[0])
        if stat is None or stat not in stats:
            raise TurnError(f"{move} needs one of these stats: {', '.join(stats)}")
        return stat, character.stats.value(stat)

    def _roll(self, value: int, adds: int) -> ActionRoll:
        action_die = self.rng.randint(1, 6)
        dice = roll_challenge_dice(self.rng)
        return evaluate_action(value, adds, self.campaign.character.momentum, action_die, dice)

    def _progress_card(self, move: str, vow: ProgressTrack | None) -> RollCard:
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
        return self._card(move, rolled_with, None, roll_progress(ticks, self.rng), self._details())

    def _card(
        self,
        move: str,
        rolled_with: str,
        action: ActionRoll | None,
        progress: ProgressRoll | None,
        details: MoveDetails,
        endurance: Endurance | None = None,
    ) -> RollCard:
        if action is not None:
            hit = action.hit
        elif progress is not None:
            hit = progress.hit
        else:
            raise TurnError(f"{move} has no roll")
        move_data = self.data.move(move)
        text = ""
        if move_data.outcomes is not None:
            outcomes = move_data.outcomes
            text = {
                Hit.STRONG: outcomes.strong_hit,
                Hit.WEAK: outcomes.weak_hit,
                Hit.MISS: outcomes.miss,
            }[hit].text
        effects = self._allowed(outcome(move, hit, details))
        if endurance is not None and endurance.fate_triggered:
            effects = (*effects, self._fate_choice(move, endurance))
        return RollCard(
            move=move,
            name=move_data.name,
            rolled_with=rolled_with,
            action=action,
            progress=progress,
            effects=effects,
            outcome_text=plain_text(text),
        )

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

        Raises:
            TurnError: If there's no card, or burning wouldn't improve its result.
        """
        pending = self._pending
        if pending is None or pending.card.action is None or not pending.card.burn_available:
            raise TurnError("burning momentum wouldn't improve this roll")
        card = pending.card
        assert card.action is not None
        burned = burn_momentum(card.action)
        self.campaign.character.reset_momentum()
        if pending.endurance is not None:
            pending.endurance = dataclasses.replace(pending.endurance, roll=burned)
        new_card = self._card(
            card.move, card.rolled_with, burned, None, pending.details, pending.endurance
        )
        pending.card = dataclasses.replace(new_card, tide=card.tide)
        self.campaign.add_log("roll", f"Burned momentum: {burned.hit.label}")
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
        self._apply(card.effects, list(choices), pending.vow)
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
        self._save()
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
            case FollowUp(move=move, amount=amount):
                vow_name = vow.name if move == "forsake_your_vow" and vow is not None else None
                campaign.follow_ups.append(OwedMove(move=move, amount=amount, vow=vow_name))
            case ClearDebility(debility=debility):
                character.clear_debility(debility)
            case MarkDebility(debility=debility):
                character.mark_debility(debility)
                campaign.add_log("outcome", f"Marked {debility}")
            case RollTable(table_id=table_id):
                result = roll_oracle(self.data, table_id, self.rng)
                campaign.add_log("outcome", f"{result.roll}: {plain_text(result.text)}")
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
        if before > 0 and character.supply == 0:
            character.mark_debility("unprepared")
            self.campaign.add_log("outcome", "Out of Supply: marked unprepared")
        excess = -amount - before
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
            campaign.bonds = min(TRACK_TICKS, campaign.bonds + times)

    def _forsake(self, vow: ProgressTrack) -> None:
        self.campaign.vows.remove(vow)
        self.campaign.add_log("outcome", f"Forsook the vow: {vow.name}")
        self.campaign.follow_ups.append(OwedMove(move="endure_stress", amount=int(vow.rank)))
        self._save()

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

    def _end_the_fight(self) -> RollCard:
        campaign = self.campaign
        if not campaign.end_fight_offered:
            raise TurnError("End the Fight needs a strong hit on a Strike or Clash first")
        campaign.end_fight_offered = False
        card = self._progress_card("end_the_fight", None)
        self._pending = _Pending(card=card, details=self._details(), vow=None)
        campaign.add_log("roll", _describe(card))
        return card

    def endure(self) -> RollCard:
        """Make the next follow-up, Endure Harm or Endure Stress, and roll it.

        The damage applies at once, before the roll. On a miss at 0, the card offers marking
        each unmarked debility of the pair, or rolling on the move's table.

        Raises:
            TurnError: If the next follow-up isn't Endure Harm or Endure Stress.
        """
        owed = self._next_follow_up(set(FATE_DEBILITIES))
        amount = owed.amount if owed.amount is not None else self._foe_harm()
        character = self.campaign.character
        action_die = self.rng.randint(1, 6)
        dice = roll_challenge_dice(self.rng)
        if owed.move == "endure_harm":
            endurance = evaluate_endure_harm(
                character.health, character.stats.iron, amount, character.momentum, action_die, dice
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
            )
            character.spirit = endurance.meter_after
        character.momentum = endurance.momentum_after
        if endurance.setback:
            self.campaign.add_log("note", _setback_note(endurance.setback))
        details = MoveDetails(meter_above_zero=endurance.meter_after > 0)
        card = self._card(owed.move, endurance.stat, endurance.roll, None, details, endurance)
        self._pending = _Pending(card=card, details=details, vow=None, endurance=endurance)
        self.campaign.add_log("roll", f"{_describe(card)} ({amount} {endurance.meter} lost first)")
        return card

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
        self._save()
        return result

    def _save(self) -> None:
        if self.path is not None:
            self.campaign.save(self.path)


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
        dice, match = "", False
    return f"{card.name} +{card.rolled_with}: {dice}, {card.hit.label}" + (
        ", match" if match else ""
    )
