"""The Textual app: a thin layer over the turn engine and the commands."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from rich.markup import escape
from rich.style import Style
from rich.text import Text
from textual import events, on, work
from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, RichLog, Static

from ironsworn_tui.abilities import AvailableBoost, BoostRef
from ironsworn_tui.campaign import Campaign, ProgressTrack
from ironsworn_tui.commands import (
    REGISTRY,
    asset_summary,
    changes_nothing,
    parse_foes,
    parse_rank,
    run_command,
)
from ironsworn_tui.moves import ATTACK, CANNOT_TELL, NO_MOVE, stat_choices
from ironsworn_tui.oracles import LIKELIHOOD_OPTIONS
from ironsworn_tui.outcomes import Choose
from ironsworn_tui.policy import OracleSuggestion, Suggestion
from ironsworn_tui.registry import CommandError, Completion, ghost_pieces
from ironsworn_tui.rules.datasworn import Datasworn, Stat
from ironsworn_tui.rules.progress import TICKS_PER_BOX, Rank
from ironsworn_tui.turn import ROLLED_FOLLOW_UPS, MoveInputs, RollCard, TurnEngine, TurnError

STAT_KEYS: dict[str, Stat] = {"e": "edge", "h": "heart", "i": "iron", "s": "shadow", "w": "wits"}
STATS: dict[str, Stat] = {stat: stat for stat in STAT_KEYS.values()}
DIGITS = "123456789"
PICK_KEYS = DIGITS + "abcdefghijklmnopqrstuvwxyz"
# The suggestion bar's lowercase letters pick stats and actions, so its moves past the
# ninth take capitals.
MOVE_KEYS = DIGITS + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PAY_KEYS: dict[str, Literal["obvious", "ask", "table"]] = {"o": "obvious", "a": "ask", "t": "table"}
# Named ANSI colors, which Textual adjusts for its light and dark themes. The outcome text is
# the plain body of each turn, so it has no style.
LOG_STYLES: dict[str, str] = {
    "message": "b",
    "explain": "dim italic",
    "roll": "cyan",
    "outcome": "",
    "choice": "magenta",
    "change": "green",
    "next": "b yellow",
    "note": "yellow",
    "command": "dim",
    "player_note": "b italic",
}
# Help isn't a log kind, because it isn't saved to the campaign log.
HELP_STYLE = "blue"
LOG_RESTORED = 200
GHOST = Style(dim=True)
GHOST_SELECTED = Style(dim=True, reverse=True)
FIELD_HINTS = {
    "vow": "The vow",
    "rank": "troublesome, dangerous, formidable, extreme, or epic",
    "foes": "A name and a rank, such as Wolf dangerous",
    "destination": "The destination",
    "treat": "yourself, someone else, or a companion",
    "amount": "How much to spend",
    "bond": "yes or no",
}
# The suggestion bar shows an option's probability only from this value up.
SHOWN_P = 0.01
# The bar's width for laying out options before the screen has a size.
SIZE_FALLBACK = 100
DICE_LABELS = ("Action die", "First challenge die", "Second challenge die")
PLACEHOLDER = "Type what your character does, or / for a command"

type Mode = Literal["idle", "thinking", "suggest", "oracle", "card", "follow_up", "offer"]


def option_name(engine: TurnEngine, option: str) -> str:
    """Return the name to show for a `move` option."""
    if option == ATTACK:
        return f"Attack ({engine.move_name(engine.move_for(ATTACK))})"
    if option in (NO_MOVE, CANNOT_TELL):
        return option.replace("_", " ").capitalize()
    return engine.move_name(option)


def oracle_option_name(option: str) -> str:
    """Return the name to show for an oracle option: `Ask likely`, or a table's short name."""
    if option in LIKELIHOOD_OPTIONS:
        return f"Ask {LIKELIHOOD_OPTIONS[option]}"
    return option


def _boost_line(boosts: list[AvailableBoost]) -> str:
    return escape("Abilities: " + ", ".join(available.label for available in boosts))


def _boxes(track: ProgressTrack) -> str:
    """Draw a progress track: a filled box for each full box, and a half-filled one for a box
    with some ticks."""
    full, ticks = divmod(track.ticks, TICKS_PER_BOX)
    part = "▣" if ticks else ""
    return "■" * full + part + "□" * (10 - full - len(part))


def _choose_prompt(choose: Choose) -> str:
    if choose.minimum == 0:
        return f"Choose up to {choose.count}:" if choose.count > 1 else "Choose one, or none:"
    if choose.minimum == choose.count:
        return f"Choose {choose.count}:" if choose.count > 1 else "Choose one:"
    return f"Choose {choose.minimum} to {choose.count}:"


def _key_range(count: int) -> str:
    """Return the keys that pick one of `count` moves for the hint, such as `1-9 A-F or `."""
    keys = MOVE_KEYS[:count]
    digits, letters = keys[: len(DIGITS)], keys[len(DIGITS) :]
    parts = [run if len(run) == 1 else f"{run[0]}-{run[-1]}" for run in (digits, letters) if run]
    return " ".join(parts) + " or " if parts else ""


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
        # A fight and a journey come first, so they show on a short screen.
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
        if campaign.journey is not None:
            j = campaign.journey
            lines += [
                "",
                "[b]Journey[/b]",
                f"{escape(j.name)} ({j.rank.name.lower()})\n  {_boxes(j)}",
            ]
        lines += ["", "[b]Vows[/b]"]
        lines += [f"{escape(v.name)} ({v.rank.name.lower()})\n  {_boxes(v)}" for v in campaign.vows]
        lines += ["", f"Bonds {campaign.bonds // TICKS_PER_BOX}/10"]
        lines += ["", "[b]Assets[/b]"]
        lines += [escape(asset_summary(data, owned)) for owned in c.assets]
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
        typed: The characters the bar took as keys since the last other key, such as the I
            that selects a move at the start of "I run". When a key the bar doesn't use
            follows, they start the text on the input line.
        oracle: The oracle suggestion being shown, in `oracle` mode.
        resume: The move suggestion to return to after an oracle question, if any.
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
    typed: str = ""
    oracle: OracleSuggestion | None = None
    resume: BarState | None = None


class SuggestionBar(Static, can_focus=True):
    """The suggestion bar: suggested moves, the roll card, and follow-ups."""

    DEFAULT_CSS = """
    SuggestionBar { height: auto; min-height: 3; border: round $accent; padding: 0 1; }
    SuggestionBar:focus { border: round $success; }
    """


class CommandInput(Input):
    """The input line, which completes `/` commands.

    After a `/`, it shows the options for the argument at the cursor as dim ghost text, such
    as `[action | theme | +20 more]`. Typing filters them, Up and Down select one, Tab
    completes it, and Escape hides them until the text changes or Tab shows them again.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("tab", "complete", "Complete", show=False),
        Binding("up", "select(-1)", "Previous option", show=False),
        Binding("down", "select(1)", "Next option", show=False),
        Binding("escape", "dismiss", "Hide options", show=False),
    ]

    def __init__(
        self, complete: Callable[[str], Completion | None], placeholder: str, id: str
    ) -> None:
        """Create the input line with the function that completes its text."""
        # Focus doesn't select the text, so a key the bar passes on adds to it.
        super().__init__(placeholder=placeholder, id=id, select_on_focus=False)
        self.complete = complete
        self.selected = 0
        self.dismissed = False
        self._completion: Completion | None = None

    @property
    def completion(self) -> Completion | None:
        """The options for the text before the cursor, or None."""
        if self.dismissed or not self.cursor_at_end or not self.value.startswith("/"):
            return None
        if self._completion is None or self._completion.text != self.value:
            self._completion = self.complete(self.value)
            self.selected = 0
        return self._completion

    def _watch_value(self, value: str) -> None:
        super()._watch_value(value)
        self.dismissed = False

    def ghost(self) -> str:
        """The ghost text after the cursor, as plain text."""
        return self._ghost().plain

    def _ghost(self) -> Text:
        completion = self.completion
        ghost = Text(end="")
        if completion is None or not self.has_focus:
            return ghost
        if completion.placeholder:
            ghost.append(f" {completion.placeholder}", GHOST)
        if completion.options:
            width = max(20, self.scrollable_content_region.width - len(self.value) - 3)
            ghost.append(" ", GHOST)
            for piece, chosen in ghost_pieces(completion.options, self.selected, width):
                ghost.append(piece, GHOST_SELECTED if chosen else GHOST)
        return ghost

    @property
    def _value(self) -> Text:
        return super()._value + self._ghost()

    def action_complete(self) -> None:
        """Complete the selected option, or move focus on when there's nothing to complete.

        After Escape, Tab shows the options again.
        """
        if self.dismissed and self.value.startswith("/"):
            self.dismissed = False
            self.refresh()
            return
        completion = self.completion
        if completion is None:
            raise SkipAction()
        if completion.options:
            self.value = completion.apply(self.selected)
            self.cursor_position = len(self.value)

    def action_select(self, step: int) -> None:
        """Select the next or previous option."""
        completion = self.completion
        if completion is None or not completion.options:
            raise SkipAction()
        self.selected = (self.selected + step) % len(completion.options)
        self.refresh()

    def action_dismiss(self) -> None:
        """Hide the options until the text changes."""
        if self.completion is None:
            raise SkipAction()
        self.dismissed = True
        self.refresh()


class InputsScreen(ModalScreen[MoveInputs | None]):
    """Asks for what a move needs first, such as a vow's name and rank."""

    DEFAULT_CSS = """
    InputsScreen { align: center middle; }
    InputsScreen > Vertical {
        width: 72; height: auto; border: round $accent; padding: 1 2; background: $surface;
    }
    InputsScreen #error { width: 100%; }
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
            yield Label("[dim]Enter next field, then roll · Esc cancel[/dim]")

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
    bond = (values.get("bond") or "no").lower()
    if bond not in ("yes", "y", "no", "n"):
        raise CommandError("bond must be yes or no")
    return MoveInputs(
        vow=values.get("vow") or None,
        rank=rank,
        foes=parse_foes(values["foes"]) if "foes" in values else (),
        destination=values.get("destination") or None,
        heal_self=treat in ("yourself", "self"),
        companion=companion,
        amount=int(amount) if amount is not None else None,
        bond=bond in ("yes", "y"),
    )


class IronswornApp(App[None]):
    """The ironsworn-tui screen: character panel, log, suggestion bar, and input line."""

    TITLE = "ironsworn-tui"
    CSS = """
    #main { height: 1fr; }
    #panel { width: 36; height: 100%; border: round $accent; padding: 0 1; }
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
            # The panel scrolls when it doesn't fit, as on an 80 by 24 screen.
            with VerticalScroll(id="panel"):
                yield CharacterPanel()
            # RichLog wraps at 78 columns unless told otherwise, which crops a narrower log.
            yield RichLog(wrap=True, markup=True, min_width=1)
        yield SuggestionBar()
        yield CommandInput(
            lambda text: REGISTRY.complete(self.engine, text),
            placeholder=PLACEHOLDER,
            id="input",
        )

    def on_mount(self) -> None:
        """Show the campaign and the recent log, then whatever the campaign owes."""
        campaign = self.engine.campaign
        for entry in campaign.log[-LOG_RESTORED:]:
            self.write_log(entry.kind, entry.text)
        if not campaign.log:
            name = campaign.character.name
            self.note(
                f"Welcome. Type what {name} does, such as I search the burned village for "
                "tracks, and press Enter. Type /help to learn how to play."
            )
        self.after_turn()

    @property
    def input(self) -> CommandInput:
        """The input line."""
        return self.query_one("#input", CommandInput)

    @property
    def bar(self) -> SuggestionBar:
        """The suggestion bar."""
        return self.query_one(SuggestionBar)

    def write_log(self, kind: str, text: str, *, starts_turn: bool = False) -> None:
        """Add a line to the log widget, after a blank line when it starts a turn: a message,
        or a typed command."""
        if kind == "note":
            text = _sentence(text)
        style = HELP_STYLE if kind == "help" else LOG_STYLES.get(kind, "")
        line = escape(text)
        log = self.query_one(RichLog)
        if (starts_turn or kind == "message") and log.lines:
            log.write("")
        log.write(f"[{style}]{line}[/{style}]" if style else line)

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
        command = text.startswith("/")
        waiting = engine.card is not None or (engine.follow_ups and not command)
        if waiting and not (command and changes_nothing(engine, text)):
            # The text stays on the input line, to send once the roll is done.
            self.note(self._finish_first())
            self.after_turn()
            return
        event.input.value = ""
        if text.startswith("/"):
            self.command(text)
            return
        if self.bar_state.mode == "oracle":
            engine.skip_oracle()
        before = len(engine.campaign.log)
        engine.log_message(text)
        self.log_new(before)
        self.bar_state = BarState(mode="thinking")
        self.input.disabled = True
        self.refresh_all()
        self._ask_id += 1
        self.ask(text, self._ask_id)

    def _finish_first(self) -> str:
        """Say what the bar waits for before the input line can send a message."""
        engine = self.engine
        if engine.card is not None:
            return "Finish the roll in the bar below first: press Enter to apply it"
        return f"Finish {engine.move_name(engine.follow_ups[0].move)} in the bar below first"

    def command(self, text: str) -> None:
        """Run a `/` command, then return to what the bar showed."""
        engine = self.engine
        before = len(engine.campaign.log)
        self.write_log("command", text, starts_turn=True)
        try:
            result = run_command(engine, text)
        except (CommandError, TurnError) as error:
            self.note(str(error))
            return
        if result.quit:
            self.exit()
            return
        self.log_new(before)
        for line in result.lines:
            self.write_log("outcome", line)
        for line in result.help:
            self.write_log("help", line)
        # A command can change what a move resolves to, as /tide does for Attack.
        self.bar_state.boosts = []
        if result.card is not None:
            self.show_card(result.card)
        elif result.oracle_question is not None:
            self.ask_oracle(result.oracle_question)
        elif result.show_moves:
            self.present(engine.full_list())
        elif self.bar_state.mode in ("suggest", "oracle") and not engine.follow_ups:
            self.refresh_all()
        else:
            self.after_turn()

    def ask_oracle(self, question: str) -> None:
        """Show the oracles for a question: every one for no question, or the decision
        model's suggestion, asked in a worker thread.

        A move suggestion on the bar comes back once the oracle question is rolled or
        skipped.
        """
        state = self.bar_state
        resume = state if state.mode == "suggest" else state.resume
        if state.mode == "oracle":
            self.engine.skip_oracle()
        if not question:
            self.present_oracle(self.engine.oracle_full_list(), resume)
            return
        self.bar_state = BarState(mode="thinking", resume=resume)
        self.input.disabled = True
        self.refresh_all()
        self._ask_id += 1
        self.decide_oracle(question, self._ask_id)

    @work(thread=True, exclusive=True, group="oracle")
    def decide_oracle(self, question: str, ask_id: int) -> None:
        """Ask the decision model about an oracle question in a worker thread."""
        suggestion = self.engine.decide_oracle(question)
        self.call_from_thread(self.answer_oracle, suggestion, ask_id)

    def answer_oracle(self, suggestion: OracleSuggestion, ask_id: int) -> None:
        """Show the oracle suggestion, unless a newer request replaced it."""
        if ask_id != self._ask_id or self.bar_state.mode != "thinking":
            return
        self.input.disabled = False
        before = len(self.engine.campaign.log)
        self.engine.accept_oracle(suggestion)
        self.log_new(before)
        self.present_oracle(suggestion, self.bar_state.resume)

    def present_oracle(self, suggestion: OracleSuggestion, resume: BarState | None) -> None:
        """Show the oracles the bar offers for a question, and focus it."""
        self.bar_state = BarState(
            mode="oracle",
            oracle=suggestion,
            options=suggestion.options,
            selected=0 if suggestion.band == "act" else None,
            resume=resume,
        )
        self.refresh_all()
        self.bar.focus()

    def _end_oracle(self) -> None:
        """Return to the move suggestion the oracle question interrupted, or to what the
        engine waits for."""
        resume = self.bar_state.resume
        engine = self.engine
        if resume is not None and engine.card is None and not engine.follow_ups:
            self.bar_state = resume
            self.refresh_all()
            self.bar.focus()
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
        before = len(self.engine.campaign.log)
        self.engine.accept(suggestion)
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
                return (
                    "[dim]Enter send · / commands · Tab complete · /help explains them · "
                    "/quit[/dim]"
                )
            case "thinking":
                return "Thinking…"
            case "suggest":
                return self._render_suggest()
            case "oracle":
                return self._render_oracle()
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
        parts: list[tuple[str, bool]] = []
        for index, option in enumerate(state.options):
            key = MOVE_KEYS[index] if index < len(MOVE_KEYS) else "·"
            p = probabilities.get(option)
            label = f"{key} {option_name(engine, option)}" + (f" {p:.2f}" if p is not None else "")
            parts.append((label, index == state.selected))
        lines = [state.message] if state.message else []
        lines += self._rows(parts)
        details = [f"Add {state.adds:+d}"]
        option = state.options[state.selected] if state.selected is not None else None
        stats = self._stats_for(option) if option is not None else ()
        if stats:
            details.insert(
                0, f"Stat {state.stat}" if state.stat in stats else self._stat_keys(stats)
            )
        lines.append("  ".join(details))
        if state.boosts:
            lines.append(_boost_line(state.boosts))
        hints = (
            f"Enter roll · {_key_range(len(state.options))}arrows move · e h i s w stat · "
            "+ - add · n no move · Esc back"
        )
        if option is not None:
            hints += self._abilities_hint(option)
        lines.append(f"[dim]{hints}[/dim]")
        return "\n".join(lines)

    def _stats_for(self, option: str) -> tuple[Stat, ...]:
        """The stats a move can roll with, or none when it doesn't ask."""
        return tuple(choice.stat for choice in stat_choices(self.engine.data, option))

    def _stat_keys(self, stats: tuple[Stat, ...]) -> str:
        """Say which keys pick a stat, such as `Stat: press h heart, s shadow, or w wits`."""
        keys = [f"{stat[0]} {stat}" for stat in stats]
        listed = keys[0] if len(keys) == 1 else ", ".join(keys[:-1]) + f", or {keys[-1]}"
        if len(keys) == 2:
            listed = f"{keys[0]} or {keys[1]}"
        return f"Stat: press {listed}"

    def _render_oracle(self) -> str:
        state = self.bar_state
        suggestion = state.oracle
        if suggestion is None:
            return ""
        decision = suggestion.decision
        probabilities: dict[str, float] = {}
        if decision is not None:
            for answer in (decision.likelihood, decision.table):
                probabilities |= answer.probabilities if answer is not None else {}
        parts: list[tuple[str, bool]] = []
        for index, option in enumerate(state.options):
            key = MOVE_KEYS[index] if index < len(MOVE_KEYS) else "·"
            p = probabilities.get(option, 0.0)
            label = f"{key} {oracle_option_name(option)}" + (f" {p:.2f}" if p >= SHOWN_P else "")
            parts.append((label, index == state.selected))
        title = "[b]Oracle[/b]" + (
            f": {escape(suggestion.question)}" if suggestion.question else ""
        )
        hints = f"Enter roll · {_key_range(len(state.options))}arrows move · Esc back"
        return "\n".join([title, *self._rows(parts), f"[dim]{hints}[/dim]"])

    def _rows(self, labels: list[tuple[str, bool]]) -> list[str]:
        """Lay out option labels in rows that fit the bar, so no label breaks across rows.

        Args:
            labels: Each label as plain text, with True for the selected one.

        Returns:
            The rows, as markup, with the selected label reversed.
        """
        width = (self.bar.content_size.width if self.is_running else 0) or SIZE_FALLBACK
        rows: list[list[str]] = [[]]
        used = 0
        for text, selected in labels:
            if rows[-1] and used + 2 + len(text) > width:
                rows.append([])
                used = 0
            used += (2 if rows[-1] else 0) + len(text)
            rows[-1].append(f"[reverse]{escape(text)}[/reverse]" if selected else escape(text))
        return ["  ".join(row) for row in rows]

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
        state = self.bar_state
        character = event.character if event.is_printable else None
        if self.bar_key(event.key, event.character or ""):
            event.stop()
            event.prevent_default()
            state.typed = state.typed + character if character else ""
        elif character and not self.input.disabled:
            # A key the bar doesn't use starts the text on the input line, so typing isn't
            # lost: / starts a command, and other keys continue the keys the bar took.
            event.stop()
            event.prevent_default()
            self.input.value = character if character == "/" else state.typed + character
            self.input.cursor_position = len(self.input.value)
            state.typed = ""
            self.input.focus()

    def bar_key(self, key: str, character: str) -> bool:
        """Act on a key for the suggestion bar's mode.

        Args:
            key: The key's name, such as `enter`.
            character: The character the key types, or an empty string.

        Returns:
            True when the bar used the key.
        """
        mode = self.bar_state.mode
        if key == "escape" and mode == "oracle":
            self.engine.skip_oracle()
            self._end_oracle()
            return True
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
                case "oracle":
                    return self._oracle_key(key, character)
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
        index = MOVE_KEYS.find(character) if character else -1
        if 0 <= index < len(state.options):
            self.select(index)
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

    def _oracle_key(self, key: str, character: str) -> bool:
        state = self.bar_state
        last = len(state.options) - 1
        index = MOVE_KEYS.find(character) if character else -1
        if 0 <= index < len(state.options):
            state.selected = index
        elif key in ("left", "up") and state.options:
            state.selected = max(0, (state.selected if state.selected is not None else 1) - 1)
        elif key in ("right", "down") and state.options:
            state.selected = min(last, (state.selected if state.selected is not None else -1) + 1)
        elif key == "enter":
            if state.selected is None or state.oracle is None:
                self.note("Pick an oracle")
                return True
            before = len(self.engine.campaign.log)
            self.engine.answer_oracle(state.options[state.selected], state.oracle.question)
            self.log_new(before)
            self._end_oracle()
            return True
        else:
            return False
        self.refresh_all()
        return True

    def _roll_selected(self) -> None:
        state = self.bar_state
        assert state.selected is not None
        option = state.options[state.selected]
        stats = self._stats_for(option)
        stat = state.stat if stats else None
        if stats and stat not in stats:
            self.note(f"{option_name(self.engine, option)} needs a stat. {self._stat_keys(stats)}")
            self.refresh_all()
            return
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
                    prompt = _choose_prompt(choose).removesuffix(":")
                    self.note(f"{prompt}: press 1 to {len(choose.options)}, then Enter")
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
