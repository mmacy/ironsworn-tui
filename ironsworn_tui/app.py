"""The Textual app: a thin layer over the turn engine and the commands."""

from dataclasses import dataclass, field
from typing import Literal

from rich.markup import escape
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, RichLog, Static

from ironsworn_tui.abilities import AvailableBoost, BoostRef
from ironsworn_tui.campaign import Campaign, ProgressTrack
from ironsworn_tui.commands import CommandError, asset_summary, parse_foes, parse_rank, run_command
from ironsworn_tui.moves import ATTACK, CANNOT_TELL, NO_MOVE, stat_choices
from ironsworn_tui.outcomes import Choose
from ironsworn_tui.policy import Suggestion
from ironsworn_tui.rules.datasworn import Datasworn, Stat
from ironsworn_tui.rules.progress import TICKS_PER_BOX, Rank
from ironsworn_tui.turn import ROLLED_FOLLOW_UPS, MoveInputs, RollCard, TurnEngine, TurnError

STAT_KEYS: dict[str, Stat] = {"e": "edge", "h": "heart", "i": "iron", "s": "shadow", "w": "wits"}
STATS: dict[str, Stat] = {stat: stat for stat in STAT_KEYS.values()}
DIGITS = "123456789"
PICK_KEYS = DIGITS + "abcdefghijklmnopqrstuvwxyz"
PAY_KEYS: dict[str, Literal["obvious", "ask", "table"]] = {"o": "obvious", "a": "ask", "t": "table"}
LOG_STYLES = {
    "message": "b",
    "roll": "cyan",
    "outcome": "green",
    "note": "yellow",
    "command": "dim",
}
FIELD_HINTS = {
    "vow": "The vow",
    "rank": "troublesome, dangerous, formidable, extreme, or epic",
    "foes": "Name rank, name rank",
    "destination": "The destination",
    "treat": "yourself, someone else, or a companion",
    "amount": "How much to spend",
}
DICE_LABELS = ("Action die", "First challenge die", "Second challenge die")

type Mode = Literal["idle", "thinking", "suggest", "card", "follow_up", "offer"]


def option_name(engine: TurnEngine, option: str) -> str:
    """Return the name to show for a `move` option."""
    if option == ATTACK:
        return "Attack"
    if option in (NO_MOVE, CANNOT_TELL):
        return option.replace("_", " ").capitalize()
    return engine.move_name(option)


def _boost_line(boosts: list[AvailableBoost]) -> str:
    return escape("Abilities: " + ", ".join(available.label for available in boosts))


def _boxes(track: ProgressTrack) -> str:
    full = track.ticks // TICKS_PER_BOX
    return "■" * full + "□" * (10 - full)


def _choose_prompt(choose: Choose) -> str:
    if choose.minimum == 0:
        return f"Choose up to {choose.count}:" if choose.count > 1 else "Choose one, or none:"
    if choose.minimum == choose.count:
        return f"Choose {choose.count}:" if choose.count > 1 else "Choose one:"
    return f"Choose {choose.minimum} to {choose.count}:"


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


class CharacterPanel(Static):
    """The character's stats, meters, vows, bonds, foes, and journey."""

    def show(self, campaign: Campaign, data: Datasworn) -> None:
        """Redraw the panel from the campaign."""
        c = campaign.character
        s = c.stats
        lines = [
            f"[b]{escape(c.name)}[/b], {escape(c.description)}",
            f"Edge {s.edge}  Heart {s.heart}  Iron {s.iron}",
            f"Shadow {s.shadow}  Wits {s.wits}",
            "",
            f"Health {c.health}  Spirit {c.spirit}  Supply {c.supply}",
            f"Momentum {c.momentum:+d} (max {c.bounds.max}, reset {c.bounds.reset})",
            f"Debilities: {', '.join(c.debilities) or 'none'}",
            f"Harm {c.harm}  Experience {c.experience}",
        ]
        if campaign.next_add:
            lines.append(f"Next move {campaign.next_add:+d}")
        lines += ["", "[b]Assets[/b]"]
        lines += [escape(asset_summary(data, owned)) for owned in c.assets]
        lines += ["", "[b]Vows[/b]"]
        lines += [f"{escape(v.name)} ({v.rank.name.lower()})\n  {_boxes(v)}" for v in campaign.vows]
        lines += ["", f"Bonds {campaign.bonds // TICKS_PER_BOX}/10"]
        if campaign.journey is not None:
            j = campaign.journey
            lines += [
                "",
                "[b]Journey[/b]",
                f"{escape(j.name)} ({j.rank.name.lower()})\n  {_boxes(j)}",
            ]
        if campaign.foes:
            who = c.name if campaign.initiative == "character" else "foe"
            lines += ["", "[b]Fight[/b]", f"Initiative: {escape(who)}"]
            if campaign.tide_armed:
                lines.append("Turn the Tide armed")
            target = campaign.target_foe()
            for foe in campaign.foes:
                mark = "> " if foe is target else "  "
                lines.append(
                    f"{mark}{escape(foe.name)} ({foe.rank.name.lower()})\n    {_boxes(foe)}"
                )
        self.update("\n".join(lines))


@dataclass
class BarState:
    """What the suggestion bar shows and the keys it takes.

    Attributes:
        mode: Which keys the bar takes.
        suggestion: The suggestion being shown, in `suggest` mode.
        options: The `move` options offered.
        selected: The index of the selected option, or None.
        stat: The stat the roll will use, for a move with a stat question.
        adds: The player's add.
        card: The roll card, in `card` mode.
        picks: The options picked for each of the card's choices so far.
        pending: The options picked for the current choice, not yet confirmed.
        message: A line shown above the options, such as "No move".
        boosts: The asset boosts turned on for the selected move or the owed endure roll.
    """

    mode: Mode = "idle"
    suggestion: Suggestion | None = None
    options: tuple[str, ...] = ()
    selected: int | None = None
    stat: Stat | None = None
    adds: int = 0
    card: RollCard | None = None
    picks: list[list[int]] = field(default_factory=list[list[int]])
    pending: list[int] = field(default_factory=list[int])
    message: str = ""
    boosts: list[AvailableBoost] = field(default_factory=list[AvailableBoost])


class SuggestionBar(Static, can_focus=True):
    """The suggestion bar: suggested moves, the roll card, and follow-ups."""

    DEFAULT_CSS = """
    SuggestionBar { height: auto; min-height: 3; border: round $accent; padding: 0 1; }
    SuggestionBar:focus { border: round $success; }
    """


class InputsScreen(ModalScreen[MoveInputs | None]):
    """Asks for what a move needs first, such as a vow's name and rank."""

    DEFAULT_CSS = """
    InputsScreen { align: center middle; }
    InputsScreen > Vertical {
        width: 60; height: auto; border: round $accent; padding: 1 2; background: $surface;
    }
    """

    def __init__(
        self, title: str, fields: tuple[str, ...], companions: dict[str, str] | None = None
    ) -> None:
        """Create the form, with a title, one input per field, and the companions Heal can
        treat, by lowercase name to asset id."""
        super().__init__()
        self.title_text = title
        self.fields = fields
        self.companions = companions or {}

    def compose(self) -> ComposeResult:
        """Lay out the title, then a label and an input for each field."""
        with Vertical():
            yield Label(f"[b]{escape(self.title_text)}[/b]")
            for name in self.fields:
                yield Label(name.capitalize())
                yield Input(id=f"field-{name}", placeholder=FIELD_HINTS[name])
            yield Label("", id="error")

    def on_key(self, event: events.Key) -> None:
        """Cancel on Escape."""
        if event.key == "escape":
            self.dismiss(None)

    @on(Input.Submitted)
    def submitted(self, event: Input.Submitted) -> None:
        """Move to the next field, or submit the form from the last one."""
        inputs = list(self.query(Input))
        index = inputs.index(event.input)
        if index < len(inputs) - 1:
            inputs[index + 1].focus()
            return
        values = {
            name: self.query_one(f"#field-{name}", Input).value.strip() for name in self.fields
        }
        try:
            self.dismiss(_inputs(values, self.companions))
        except CommandError as error:
            self.query_one("#error", Label).update(_sentence(str(error)))


class PickScreen(ModalScreen[list[int] | None]):
    """Picks any of a short list of items with the digit keys, then Enter."""

    DEFAULT_CSS = """
    PickScreen { align: center middle; }
    PickScreen > Vertical {
        width: 80; height: auto; border: round $accent; padding: 1 2; background: $surface;
    }
    """

    def __init__(self, title: str, items: list[str], picked: list[int]) -> None:
        """Create the picker, with a title, the items, and the ones already picked."""
        super().__init__()
        self.title_text = title
        self.items = items
        self.picked = list(picked)

    def compose(self) -> ComposeResult:
        """Lay out the title, the items, and the keys."""
        with Vertical():
            yield Label(f"[b]{escape(self.title_text)}[/b]")
            yield Label(self._items_text(), id="items")
            last = self.key_for(len(self.items) - 1)
            yield Label(f"[dim]1-{last} turn on or off · Enter done · Esc cancel[/dim]")

    def key_for(self, index: int) -> str:
        """The key that picks an item: 1 to 9, then letters."""
        return PICK_KEYS[index]

    def index_for(self, character: str) -> int | None:
        """The item a key picks, or None."""
        index = PICK_KEYS.find(character) if character else -1
        return index if 0 <= index < len(self.items) else None

    def _items_text(self) -> str:
        lines: list[str] = []
        for index, item in enumerate(self.items):
            mark = "[x]" if index in self.picked else "[ ]"
            lines.append(f"{self.key_for(index)} {mark} {escape(item)}")
        return "\n".join(lines)

    def on_key(self, event: events.Key) -> None:
        """Toggle an item, finish, or cancel."""
        character = event.character or ""
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter":
            self.dismiss(sorted(self.picked))
        elif (index := self.index_for(character)) is not None:
            if index in self.picked:
                self.picked.remove(index)
            else:
                self.picked.append(index)
            self.query_one("#items", Label).update(self._items_text())
        else:
            return
        event.stop()


class AbilitiesScreen(PickScreen):
    """Picks the asset boosts to turn on for a move."""


class DiceScreen(PickScreen):
    """Picks the dice to reroll."""


def _inputs(values: dict[str, str], companions: dict[str, str]) -> MoveInputs:
    rank: Rank | None = parse_rank(values["rank"]) if "rank" in values else None
    treat = (values.get("treat") or "yourself").lower()
    companion = companions.get(treat)
    if treat not in ("yourself", "someone else", "self", "other") and companion is None:
        raise CommandError("treat must be yourself, someone else, or one of your companions")
    amount = values.get("amount")
    if amount is not None and not amount.isdigit():
        raise CommandError("amount must be a number")
    return MoveInputs(
        vow=values.get("vow") or None,
        rank=rank,
        foes=parse_foes(values["foes"]) if "foes" in values else (),
        destination=values.get("destination") or None,
        heal_self=treat in ("yourself", "self"),
        companion=companion,
        amount=int(amount) if amount is not None else None,
    )


class IronswornApp(App[None]):
    """The ironsworn-tui screen: character panel, log, suggestion bar, and input line."""

    TITLE = "ironsworn-tui"
    CSS = """
    #main { height: 1fr; }
    CharacterPanel { width: 36; height: 100%; border: round $accent; padding: 0 1; }
    RichLog { border: round $accent; }
    """

    def __init__(self, engine: TurnEngine) -> None:
        """Create the app for a turn engine."""
        super().__init__()
        self.engine = engine
        self.bar_state = BarState()
        self._ask_id = 0

    def compose(self) -> ComposeResult:
        """Lay out the four parts."""
        with Horizontal(id="main"):
            yield CharacterPanel()
            yield RichLog(wrap=True, markup=True)
        yield SuggestionBar()
        yield Input(placeholder="Action or /command", id="input")

    def on_mount(self) -> None:
        """Show the campaign and the recent log, then whatever the campaign owes."""
        for entry in self.engine.campaign.log[-50:]:
            self.write_log(entry.kind, entry.text)
        self.after_turn()

    @property
    def input(self) -> Input:
        """The input line."""
        return self.query_one("#input", Input)

    @property
    def bar(self) -> SuggestionBar:
        """The suggestion bar."""
        return self.query_one(SuggestionBar)

    def write_log(self, kind: str, text: str) -> None:
        """Add a line to the log widget."""
        if kind == "note":
            text = _sentence(text)
        style = LOG_STYLES.get(kind, "")
        line = escape(text)
        self.query_one(RichLog).write(f"[{style}]{line}[/{style}]" if style else line)

    def note(self, text: str) -> None:
        """Show a note in the log widget without adding it to the campaign."""
        self.write_log("note", text)

    def refresh_all(self) -> None:
        """Redraw the panel and the suggestion bar."""
        self.query_one(CharacterPanel).show(self.engine.campaign, self.engine.data)
        self.bar.update(self.render_bar())

    def log_new(self, before: int) -> None:
        """Write the campaign log entries added since `before`."""
        for entry in self.engine.campaign.log[before:]:
            self.write_log(entry.kind, entry.text)

    @on(Input.Submitted, "#input")
    def submit(self, event: Input.Submitted) -> None:
        """Send a message, or run a command."""
        text = event.value.strip()
        engine = self.engine
        if not text or self.bar_state.mode == "thinking":
            return
        event.input.value = ""
        if engine.card is not None or (engine.follow_ups and not text.startswith("/")):
            self.note("Finish the roll first")
            self.after_turn()
            return
        if text.startswith("/"):
            self.command(text)
            return
        before = len(engine.campaign.log)
        engine.log_message(text)
        self.log_new(before)
        self.bar_state = BarState(mode="thinking")
        self.input.disabled = True
        self.refresh_all()
        self._ask_id += 1
        self.ask(text, self._ask_id)

    def command(self, text: str) -> None:
        """Run a `/` command, then return to what the bar showed."""
        engine = self.engine
        before = len(engine.campaign.log)
        self.write_log("command", text)
        try:
            result = run_command(engine, text)
        except (CommandError, TurnError) as error:
            self.note(str(error))
            return
        self.log_new(before)
        for line in result.lines:
            self.write_log("outcome", line)
        # A command can change what a move resolves to, as /tide does for Attack.
        self.bar_state.boosts = []
        if result.card is not None:
            self.show_card(result.card)
        elif result.show_moves:
            self.present(engine.full_list())
        elif self.bar_state.mode == "suggest" and not engine.follow_ups:
            self.refresh_all()
        else:
            self.after_turn()

    @work(thread=True, exclusive=True)
    def ask(self, text: str, ask_id: int) -> None:
        """Ask the decision model in a worker thread, so the screen stays responsive.

        The worker only reads the campaign. Its result reaches the screen through
        `call_from_thread`.
        """
        suggestion = self.engine.decide(text)
        self.call_from_thread(self.answer, suggestion, ask_id)

    def answer(self, suggestion: Suggestion, ask_id: int) -> None:
        """Show the decision model's answer, unless a newer message replaced it."""
        if ask_id != self._ask_id or self.bar_state.mode != "thinking":
            return
        self.input.disabled = False
        self.engine.accept(suggestion)
        if suggestion.note is not None:
            before = len(self.engine.campaign.log)
            self.engine.campaign.add_log("note", suggestion.note)
            self.engine.save()
            self.log_new(before)
        self.present(suggestion)

    def present(self, suggestion: Suggestion) -> None:
        """Show what the suggestion bar offers, and focus it."""
        selected = 0 if suggestion.band in ("act", "confirm") else None
        state = BarState(mode="suggest", suggestion=suggestion, options=suggestion.options)
        if suggestion.band == "no_roll":
            state.message = "No move"
        self.bar_state = state
        self.select(selected)
        self.refresh_all()
        self.bar.focus()

    def select(self, index: int | None) -> None:
        """Select an option, and preselect the stat the model suggests for it."""
        state = self.bar_state
        if index == state.selected and index is not None:
            return
        state.selected = index
        state.stat = None
        state.boosts = []
        if index is None or state.suggestion is None:
            return
        decision = state.suggestion.decision
        answer = decision.stat_for(state.options[index]) if decision is not None else None
        if answer is not None:
            state.stat = STATS.get(answer.choice)

    def render_bar(self) -> str:
        """Render the suggestion bar for its mode."""
        state = self.bar_state
        engine = self.engine
        match state.mode:
            case "idle":
                commands = (
                    "/moves · /oracle · /ask · /vow · /scene · /target · /tide · /adjust · "
                    "/endure · /asset · /effects"
                )
                return f"[dim]Enter send · {commands}[/dim]"
            case "thinking":
                return "Thinking…"
            case "suggest":
                return self._render_suggest()
            case "card":
                return self._render_card()
            case "follow_up":
                owed = engine.follow_ups[0]
                name = engine.move_name(owed.move)
                if owed.move == "pay_the_price":
                    hint = "o obvious outcome · a ask the oracle · t roll the table"
                elif owed.move == "forsake_your_vow":
                    hint = "Enter forsake"
                else:
                    amount = f" ({owed.amount})" if owed.amount is not None else ""
                    hint = f"Enter roll{amount}" + self._abilities_hint(owed.move)
                lines = [f"[b]{name}[/b]"]
                if self.bar_state.boosts:
                    lines.append(_boost_line(self.bar_state.boosts))
                return "\n".join([*lines, f"[dim]{hint}[/dim]"])
            case "offer":
                lines = ["[b]End the Fight[/b]"]
                if self.bar_state.boosts:
                    lines.append(_boost_line(self.bar_state.boosts))
                hint = "f end the fight · Esc continue" + self._abilities_hint("end_the_fight")
                return "\n".join([*lines, f"[dim]{hint}[/dim]"])

    def _render_suggest(self) -> str:
        state = self.bar_state
        engine = self.engine
        decision = state.suggestion.decision if state.suggestion else None
        probabilities = decision.move.probabilities if decision and decision.move else {}
        parts: list[str] = []
        for index, option in enumerate(state.options):
            key = DIGITS[index] if index < len(DIGITS) else "·"
            p = probabilities.get(option)
            label = f"{key} {option_name(engine, option)}" + (f" {p:.2f}" if p is not None else "")
            parts.append(f"[reverse]{label}[/reverse]" if index == state.selected else label)
        lines = [state.message] if state.message else []
        lines.append("  ".join(parts))
        details = [f"Add {state.adds:+d}"]
        option = state.options[state.selected] if state.selected is not None else None
        if option is not None and stat_choices(engine.data, option):
            details.insert(0, f"Stat {state.stat or 'not set'}")
        lines.append("  ".join(details))
        if state.boosts:
            lines.append(_boost_line(state.boosts))
        hints = "Enter roll · 1-9 or arrows move · e h i s w stat · + - add · n no move · Esc back"
        if option is not None:
            hints += self._abilities_hint(option)
        lines.append(f"[dim]{hints}[/dim]")
        return "\n".join(lines)

    def _abilities_hint(self, option: str) -> str:
        count = len(self._available(option))
        return f" · a abilities ({count})" if count else ""

    def _available(self, option: str) -> tuple[AvailableBoost, ...]:
        if option in (NO_MOVE, CANNOT_TELL):
            return ()
        return self.engine.boosts_for(option)

    def _pick_boosts(self, option: str) -> None:
        """Open the abilities picker for a move, and keep what the player turns on."""
        available = list(self._available(option))
        if not available:
            self.note("No abilities apply to this move")
            return
        state = self.bar_state
        picked = [index for index, a in enumerate(available) if a in state.boosts]

        def done(indices: list[int] | None) -> None:
            if indices is not None and self.bar_state is state:
                state.boosts = [available[index] for index in indices]
            self.refresh_all()
            self.bar.focus()

        title = f"Abilities for {option_name(self.engine, option)}"
        self.push_screen(AbilitiesScreen(title, [a.label for a in available], picked), done)

    def _refs(self) -> list[BoostRef]:
        return [available.ref for available in self.bar_state.boosts]

    def _chooses(self) -> list[Choose]:
        card = self.bar_state.card
        return [effect for effect in card.effects if isinstance(effect, Choose)] if card else []

    def _render_card(self) -> str:
        state = self.bar_state
        card = state.card
        if card is None:
            return ""
        lines = [f"[b]{card.name}[/b] +{card.rolled_with}: {card.hit.label}"]
        if card.boosts:
            lines.append(escape("With " + ", ".join(card.boosts)))
        lines.append(escape(card.outcome_text))
        chooses = self._chooses()
        keys = ["Enter apply"]
        if len(state.picks) < len(chooses):
            choose = chooses[len(state.picks)]
            lines.append(_choose_prompt(choose))
            for index, option in enumerate(choose.options):
                label = f"{index + 1} {escape(option.label)}"
                lines.append(
                    f"  [reverse]{label}[/reverse]" if index in state.pending else f"  {label}"
                )
            keys.insert(0, f"1-{len(choose.options)} choose")
        if card.can_reroll:
            keys.append("r reroll")
        if card.can_late_add:
            keys.append("+ add after rolling")
        if card.burn_available:
            keys.append("b burn momentum")
        lines.append("[dim]" + " · ".join(keys) + "[/dim]")
        return "\n".join(lines)

    def show_card(self, card: RollCard) -> None:
        """Show a roll card in the suggestion bar."""
        self.bar_state = BarState(mode="card", card=card)
        self.input.disabled = False
        self.refresh_all()
        self.bar.focus()

    def after_turn(self) -> None:
        """Show what the engine is waiting for: a roll card, a follow-up, or the offer."""
        engine = self.engine
        self.input.disabled = False
        if engine.card is not None:
            self.show_card(engine.card)
            return
        if engine.follow_ups:
            self.bar_state = BarState(mode="follow_up")
        elif engine.campaign.end_fight_offered:
            self.bar_state = BarState(mode="offer")
        else:
            self.bar_state = BarState()
        self.refresh_all()
        if self.bar_state.mode == "idle":
            self.input.focus()
        else:
            self.bar.focus()

    def on_key(self, event: events.Key) -> None:
        """Handle the suggestion bar's keys while it has focus."""
        if not isinstance(self.focused, SuggestionBar):
            return
        if self.bar_key(event.key, event.character or ""):
            event.stop()
            event.prevent_default()

    def bar_key(self, key: str, character: str) -> bool:
        """Act on a key for the suggestion bar's mode.

        Args:
            key: The key's name, such as `enter`.
            character: The character the key types, or an empty string.

        Returns:
            True when the bar used the key.
        """
        mode = self.bar_state.mode
        if key == "escape" and mode in ("suggest", "offer"):
            if mode == "suggest":
                self.engine.skip()
            else:
                self.engine.decline_end_fight()
            self.bar_state = BarState()
            self.refresh_all()
            self.input.focus()
            return True
        try:
            match mode:
                case "suggest":
                    return self._suggest_key(key, character)
                case "card":
                    return self._card_key(key, character)
                case "follow_up":
                    return self._follow_up_key(key, character)
                case "offer" if character == "f":
                    self._make("end_the_fight", None, 0, MoveInputs(), self._refs())
                    return True
                case "offer" if character == "a":
                    self._pick_boosts("end_the_fight")
                    return True
                case _:
                    return False
        except (TurnError, CommandError) as error:
            self.note(str(error))
            self.refresh_all()
            return True

    def _suggest_key(self, key: str, character: str) -> bool:
        state = self.bar_state
        last = len(state.options) - 1
        if character and character in DIGITS and int(character) <= len(state.options):
            self.select(int(character) - 1)
        elif key in ("left", "up") and state.options:
            self.select(max(0, (state.selected if state.selected is not None else 1) - 1))
        elif key in ("right", "down") and state.options:
            self.select(min(last, (state.selected if state.selected is not None else -1) + 1))
        elif character in STAT_KEYS:
            state.stat = STAT_KEYS[character]
        elif character == "a" and state.selected is not None:
            self._pick_boosts(state.options[state.selected])
            return True
        elif character == "n":
            before = len(self.engine.campaign.log)
            self.engine.no_move()
            self.log_new(before)
            self.after_turn()
            return True
        elif character == "+":
            state.adds += 1
        elif character == "-":
            state.adds -= 1
        elif key == "enter":
            if state.selected is None:
                self.note("Pick a move")
            else:
                self._roll_selected()
                return True
        else:
            return False
        self.refresh_all()
        return True

    def _roll_selected(self) -> None:
        state = self.bar_state
        assert state.selected is not None
        option = state.options[state.selected]
        stat = state.stat if stat_choices(self.engine.data, option) else None
        fields = self.engine.inputs_needed(option)
        if any(available.boost.unleash for available in state.boosts):
            fields = (*fields, "amount")
        adds = state.adds
        boosts = self._refs()
        if not fields:
            self._make(option, stat, adds, MoveInputs(), boosts)
            return

        def done(inputs: MoveInputs | None) -> None:
            if inputs is None:
                return
            try:
                self._make(option, stat, adds, inputs, boosts)
            except TurnError as error:
                self.note(str(error))
                self.refresh_all()

        screen = InputsScreen(option_name(self.engine, option), fields, self.engine.companions())
        self.push_screen(screen, done)

    def _make(
        self,
        option: str,
        stat: Stat | None,
        adds: int,
        inputs: MoveInputs,
        boosts: list[BoostRef] | None = None,
    ) -> None:
        before = len(self.engine.campaign.log)
        card = self.engine.make_move(
            option, stat=stat, adds=adds, inputs=inputs, boosts=boosts or []
        )
        self.log_new(before)
        if card is None:
            self.after_turn()
        else:
            self.show_card(card)

    def _card_key(self, key: str, character: str) -> bool:
        state = self.bar_state
        chooses = self._chooses()
        current = len(state.picks)
        if character and character in DIGITS and current < len(chooses):
            index = int(character) - 1
            choose = chooses[current]
            if index >= len(choose.options):
                return True
            if index in state.pending:
                state.pending.remove(index)
            elif choose.count == 1:
                state.pending = [index]
            elif len(state.pending) < choose.count:
                state.pending.append(index)
        elif character == "r" and state.card is not None and state.card.can_reroll:
            self._pick_dice(state.card)
            return True
        elif character == "+" and state.card is not None and state.card.can_late_add:
            before = len(self.engine.campaign.log)
            state.card = self.engine.late_add()
            state.picks = []
            state.pending = []
            self.log_new(before)
        elif character == "b" and state.card is not None and state.card.burn_available:
            before = len(self.engine.campaign.log)
            state.card = self.engine.burn()
            state.picks = []
            state.pending = []
            self.log_new(before)
        elif key == "enter":
            if current < len(chooses):
                choose = chooses[current]
                if not choose.minimum <= len(state.pending) <= choose.count:
                    self.note(_choose_prompt(choose).removesuffix(":"))
                    return True
                state.picks.append(state.pending)
                state.pending = []
                if len(state.picks) < len(chooses):
                    self.refresh_all()
                    return True
            before = len(self.engine.campaign.log)
            try:
                self.engine.resolve(state.picks)
            except TurnError:
                state.picks = []
                raise
            self.log_new(before)
            self.after_turn()
            return True
        else:
            return False
        self.refresh_all()
        return True

    def _pick_dice(self, card: RollCard) -> None:
        """Open the dice picker, and reroll the dice the player picks."""
        labels: list[str] = list(DICE_LABELS[0 if card.action is not None else 1 :])
        offset = 0 if card.action is not None else 1
        state = self.bar_state

        def done(indices: list[int] | None) -> None:
            if indices and self.bar_state is state:
                before = len(self.engine.campaign.log)
                try:
                    state.card = self.engine.reroll([index + offset for index in indices])
                except TurnError as error:
                    self.note(str(error))
                state.picks = []
                state.pending = []
                self.log_new(before)
            self.refresh_all()
            self.bar.focus()

        self.push_screen(DiceScreen("Reroll which dice?", labels, []), done)

    def _follow_up_key(self, key: str, character: str) -> bool:
        engine = self.engine
        owed = engine.follow_ups[0]
        before = len(engine.campaign.log)
        if owed.move == "pay_the_price" and character in PAY_KEYS:
            engine.pay_the_price(PAY_KEYS[character])
        elif key == "enter" and owed.move == "forsake_your_vow":
            engine.forsake()
        elif character == "a" and owed.move in ROLLED_FOLLOW_UPS:
            self._pick_boosts(owed.move)
            return True
        elif key == "enter" and owed.move in ROLLED_FOLLOW_UPS:
            card = engine.roll_follow_up(self._refs())
            self.log_new(before)
            if card is None:
                self.after_turn()
            else:
                self.show_card(card)
            return True
        else:
            return False
        self.log_new(before)
        self.after_turn()
        return True
