"""The command registry: each command's arguments, help, parsing, and completion.

The registry is the one description of the `/` commands. Parsing, completion on the
input line, and help all read it, so they can't disagree. It has no UI code.
"""

import difflib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ironsworn_tui.turn import RollCard, TurnEngine

HELP = "help"


class CommandError(ValueError):
    """The command or its arguments aren't valid."""


class UsageError(CommandError):
    """An argument isn't valid, so the error also shows the command's usage."""


@dataclass(frozen=True)
class CommandResult:
    """What a command did.

    Every command logs what it changes to the campaign log itself.

    Attributes:
        lines: Lines to show that aren't in the campaign log, such as the vow list.
        card: A roll card, when the command made a move (`/vow swear` or `/vow fulfill`).
        show_moves: True when the suggestion bar should show the full move list.
        help: Help lines to show, which aren't in the campaign log either.
        quit: True when the app should quit.
    """

    lines: tuple[str, ...] = ()
    card: RollCard | None = None
    show_moves: bool = False
    help: tuple[str, ...] = ()
    quit: bool = False


type Values = tuple[str, ...]
"""The arguments parsed so far, one string for each argument position."""

type Provider = Callable[[TurnEngine, Values], Sequence[str]]
"""Returns the current options for an argument, given the arguments before it."""

type Handler = Callable[[TurnEngine, Values], CommandResult]
"""Runs a command with its parsed arguments."""


@dataclass(frozen=True)
class Arg:
    """One argument position of a command.

    Attributes:
        name: The argument's name in the usage, such as `table`.
        options: The values it takes: a fixed tuple, or a provider for values that depend on
            the campaign, such as vow names. Without `free`, the argument must be one of them.
        optional: True when the command runs without it.
        free: True when it also takes text that isn't one of the options.
        rest: True when it takes the rest of the line, such as a scene's text.
        number: True when it must be a whole number, such as `-2`.
        repeat: True when it takes any number of options, such as stat changes.
    """

    name: str
    options: tuple[str, ...] | Provider = ()
    optional: bool = False
    free: bool = False
    rest: bool = False
    number: bool = False
    repeat: bool = False

    def choices(self, engine: TurnEngine, values: Values) -> tuple[str, ...]:
        """Return the argument's current options."""
        options = self.options
        if callable(options):
            return tuple(options(engine, values))
        return options

    @property
    def usage(self) -> str:
        """The argument as the usage shows it, such as `<table>` or `[on|off]`."""
        options = self.options
        if not callable(options) and 0 < len(options) <= 3 and not self.free:
            text = "|".join(options)
        else:
            text = f"<{self.name}>"
        if self.repeat:
            return f"[{text} ...]"
        return f"[{text}]" if self.optional else text


@dataclass(frozen=True)
class Command:
    """A command or a subcommand.

    Attributes:
        name: The name, such as `oracle` or `swear`.
        summary: One line that says what it does.
        run: Runs it, or None for a command that needs a subcommand.
        args: Its arguments, for a command without subcommands.
        subcommands: Its subcommands, such as `/vow swear`.
        help: Longer help for a new player, one paragraph per item.
        examples: Example commands.
        extra: More help lines shown after the usage, such as the oracle tables.
    """

    name: str
    summary: str
    run: Handler | None = None
    args: tuple[Arg, ...] = ()
    subcommands: tuple[Command, ...] = ()
    help: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()

    def find(self, name: str) -> Command | None:
        """Return the subcommand with a name, in any case, or None."""
        return next((sub for sub in self.subcommands if sub.name == name.lower()), None)

    @property
    def takes_more(self) -> bool:
        """True when the command has arguments or subcommands after its name."""
        return bool(self.args or self.subcommands)


@dataclass(frozen=True)
class Parsed:
    """A parsed command line.

    Attributes:
        path: The command, then the subcommand, if any.
        values: The arguments, one for each argument position given.
        help: True when the line asked for help instead.
    """

    path: tuple[Command, ...]
    values: Values = ()
    help: bool = False


@dataclass(frozen=True)
class Completion:
    """The options for the argument the input line is on.

    Attributes:
        text: The input line's text.
        start: Where the part being completed starts in `text`.
        options: The options that match what's typed, best first.
        more: For each option, True when more arguments can follow it, so completing it adds
            a space.
        placeholder: A name for free text, such as `<text>`, or an empty string.
    """

    text: str
    start: int
    options: tuple[str, ...]
    more: tuple[bool, ...]
    placeholder: str = ""

    def apply(self, index: int) -> str:
        """Return the text with the option at `index` completed."""
        space = " " if self.more[index] else ""
        return self.text[: self.start] + self.options[index] + space


def _key(text: str) -> str:
    """Return text for matching: lowercase, with `-` and spaces read as `_`.

    Each character maps to one character, so a match's length is the same in the text.
    """
    return text.lower().replace("-", "_").replace(" ", "_")


def filter_options(options: Sequence[str], typed: str) -> tuple[str, ...]:
    """Return the options that match what's typed: those that start with it, then those that
    contain it, each in their order. Case, `-`, `_`, and spaces don't matter."""
    key = _key(typed)
    starts = [option for option in options if _key(option).startswith(key)]
    contains = [option for option in options if key in _key(option) and option not in starts]
    return (*starts, *contains)


def _match(text: str, options: Sequence[str], *, at_end: bool) -> tuple[str, str] | None:
    """Return the longest option that `text` starts with as whole words, and the text after it.

    Args:
        text: The text, with no leading space.
        options: The options.
        at_end: True when an option can also end the text. Completion passes False, so an
            option counts only once a space follows it.
    """
    best: str | None = None
    for option in options:
        size = len(option)
        if _key(text[:size]) != _key(option):
            continue
        ends = size == len(text) and at_end
        if (ends or text[size : size + 1].isspace()) and (best is None or size > len(best)):
            best = option
    if best is None:
        return None
    return best, text[len(best) :].lstrip()


def _split(text: str) -> tuple[str, str]:
    """Split off the first word."""
    word, _, rest = text.strip().partition(" ")
    return word, rest.lstrip()


def ghost_pieces(options: Sequence[str], selected: int, width: int) -> tuple[tuple[str, bool], ...]:
    """Lay out options as `[a | b | c]` in at most `width` characters.

    With too many to fit, it shows a window around the selected option and counts the
    rest, as `[+3 more | d | e | +40 more]`.

    Args:
        options: The options.
        selected: The index of the selected option.
        width: The most characters to use.

    Returns:
        The pieces in order, each with True for the selected option.
    """

    def size(start: int, end: int) -> int:
        shown = [*options[start:end]]
        if start:
            shown.append(f"+{start} more")
        if end < len(options):
            shown.append(f"+{len(options) - end} more")
        return sum(len(item) for item in shown) + 3 * (len(shown) - 1) + 2

    start, end = selected, selected + 1
    grew = True
    while grew:
        grew = False
        if end < len(options) and size(start, end + 1) <= width:
            end += 1
            grew = True
        if start > 0 and size(start - 1, end) <= width:
            start -= 1
            grew = True
    items: list[tuple[str, bool]] = []
    if start:
        items.append((f"+{start} more", False))
    items += [(options[index], index == selected) for index in range(start, end)]
    if end < len(options):
        items.append((f"+{len(options) - end} more", False))
    pieces: list[tuple[str, bool]] = [("[", False)]
    for index, item in enumerate(items):
        if index:
            pieces.append((" | ", False))
        pieces.append(item)
    pieces.append(("]", False))
    return tuple(pieces)


@dataclass(frozen=True)
class Registry:
    """Every command, and the parsing, completion, and help they share.

    Attributes:
        commands: The commands, in the order `/help` lists them.
    """

    commands: tuple[Command, ...]

    @property
    def names(self) -> tuple[str, ...]:
        """The command names."""
        return tuple(command.name for command in self.commands)

    def find(self, name: str) -> Command | None:
        """Return the command with a name, in any case, or None."""
        return next((c for c in self.commands if c.name == name.lower()), None)

    def parse(self, engine: TurnEngine, text: str) -> Parsed:
        """Parse a command line.

        Args:
            engine: The turn engine, for options such as vow names.
            text: The line, starting with `/`.

        Returns:
            The command, its subcommand, and the arguments.

        Raises:
            CommandError: If the command, a subcommand, or an argument isn't valid. The
                message shows the usage and points to the command's help.
        """
        name, rest = _split(text.strip().removeprefix("/"))
        command = self.find(name)
        if command is None:
            raise CommandError(self._unknown(name))
        path = [command]
        while True:
            word, after = _split(rest)
            if word.lower() == HELP:
                return Parsed(tuple(path), help=True)
            if not command.subcommands or (not word and command.run is not None):
                break
            sub = command.find(word)
            if sub is None:
                names = ", ".join(self._sub_names(command))
                problem = f"/{command.name} needs one of: {names}"
                if word:
                    problem = f"/{command.name} has no {word!r} option. It has: {names}"
                raise CommandError(self.usage_error(problem, tuple(path)))
            command = sub
            path.append(sub)
            rest = after
        try:
            values = self._parse_args(engine, command.args, rest)
        except UsageError as error:
            raise CommandError(self.usage_error(str(error), tuple(path))) from None
        return Parsed(tuple(path), values)

    def _parse_args(self, engine: TurnEngine, args: tuple[Arg, ...], rest: str) -> Values:
        values: list[str] = []
        rest = rest.strip()
        for index, arg in enumerate(args):
            if not rest:
                if arg.optional or arg.repeat:
                    break
                raise UsageError(_missing(arg, arg.choices(engine, tuple(values))))
            while rest:
                last = index == len(args) - 1
                value, rest = self._take(engine, arg, tuple(values), rest, last=last)
                values.append(value)
                if not arg.repeat:
                    break
        if rest:
            raise UsageError(f"there's more than it takes: {rest!r}")
        return tuple(values)

    def _take(
        self, engine: TurnEngine, arg: Arg, values: Values, rest: str, *, last: bool
    ) -> tuple[str, str]:
        """Take one argument's value from the front of `rest`."""
        if arg.rest:
            return rest, ""
        options = arg.choices(engine, values)
        found = _match(rest, options, at_end=True)
        if found is not None:
            return found
        word, after = _split(rest)
        if arg.number:
            try:
                int(word)
            except ValueError:
                raise UsageError(f"{word!r} isn't a number") from None
            if not options or arg.free:
                return word, after
        if arg.free:
            return word, after
        shown = rest if last and not arg.repeat else word
        if 0 < len(options) <= 12:
            raise UsageError(f"{arg.name} must be one of: {', '.join(options)}, not {shown!r}")
        raise UsageError(f"no {arg.name} named {shown!r}")

    def complete(self, engine: TurnEngine, text: str) -> Completion | None:
        """Return the options for the argument at the end of an input line.

        Args:
            engine: The turn engine, for options such as vow names.
            text: The text up to the cursor.

        Returns:
            The options that match what's typed, or None when the text doesn't start with
            `/` or there's nothing more to complete.
        """
        if not text.startswith("/"):
            return None
        body = text[1:]
        if " " not in body:
            commands = [self.find(name) for name in filter_options(self.names, body)]
            found = [command for command in commands if command is not None]
            return Completion(
                text,
                1,
                tuple(command.name for command in found),
                tuple(command.takes_more for command in found),
            )
        name, _, _ = body.partition(" ")
        command = self.find(name)
        if command is None:
            return None
        position = 1 + len(name)
        while command.subcommands:
            start, rest = _skip(text, position)
            if " " not in rest:
                names = filter_options([*self._sub_names(command), HELP], rest)
                return Completion(text, start, names, self._more(command, names))
            word, _, _ = rest.partition(" ")
            sub = command.find(word)
            if sub is None:
                return None
            command = sub
            position = start + len(word)
        return self._complete_args(engine, command, text, position)

    def _more(self, command: Command, names: Sequence[str]) -> tuple[bool, ...]:
        found = [command.find(name) for name in names]
        return tuple(sub is not None and sub.takes_more for sub in found)

    def _complete_args(
        self, engine: TurnEngine, command: Command, text: str, position: int
    ) -> Completion | None:
        values: list[str] = []
        index = 0
        args = command.args
        while index < len(args):
            arg = args[index]
            start, rest = _skip(text, position)
            first = not values
            options = arg.choices(engine, tuple(values))
            if first and HELP not in options:
                options = (*options, HELP)
            more = index < len(args) - 1 or arg.repeat
            if arg.rest:
                names = filter_options(options, rest)
                placeholder = "" if rest else f"<{arg.name}>"
                return Completion(text, start, names, (False,) * len(names), placeholder)
            found = _match(rest, options, at_end=False)
            if found is None and (" " not in rest or filter_options(options, rest)):
                names = filter_options(options, rest)
                free = arg.free or arg.number or not arg.choices(engine, tuple(values))
                placeholder = f"<{arg.name}>" if free and not rest else ""
                flags = tuple(more and name != HELP for name in names)
                return Completion(text, start, names, flags, placeholder)
            if found is None:
                word, _, _ = rest.partition(" ")
                if not (arg.free or arg.number):
                    return None
                value = word
                position = start + len(word)
            else:
                value = found[0]
                position = len(text) - len(found[1])
                if value == HELP and first:
                    return None
            values.append(value)
            if not arg.repeat:
                index += 1
        return None

    def help(self, path: Sequence[Command]) -> tuple[str, ...]:
        """Return the help for a command or a subcommand.

        It has the summary, the longer help, the usage, the examples, the subcommands or
        the options, and any extra lines.
        """
        command = path[-1]
        prefix = "/" + " ".join(c.name for c in path)
        lines = [f"{prefix}: {command.summary}", *command.help]
        lines += [f"Usage: {usage}" for usage in self.usages(path)]
        lines += [f"Example: {example}" for example in command.examples]
        if command.subcommands:
            lines.append("Options:")
            lines += [f"  {sub.name}: {sub.summary}" for sub in command.subcommands]
            first = command.subcommands[0].name
            lines.append(f"Add help after an option for more, such as {prefix} {first} help.")
        lines += command.extra
        return tuple(lines)

    def overview(self) -> tuple[str, ...]:
        """Return the list `/help` shows: each command with its summary."""
        lines = [
            "Type what your character does, such as I search the ruins for tracks, and press "
            "Enter. The bar below the log then offers the moves that fit. A move is a rule for a "
            "risky action: pick one with its key, pick a stat if it asks for one, and press "
            "Enter to roll. If no roll is needed, press n. Esc goes back to typing.",
            "Commands:",
        ]
        lines += [f"/{command.name}: {command.summary}" for command in self.commands]
        lines.append("Add help after any command for more, such as /oracle help.")
        lines.append("Type / and press Tab to complete a command or its options.")
        lines.append("The campaign saves after every change. /quit or Ctrl+Q leaves the app.")
        return tuple(lines)

    def usages(self, path: Sequence[Command]) -> tuple[str, ...]:
        """Return the usage lines for a command: one, or one for each subcommand."""
        command = path[-1]
        prefix = "/" + " ".join(c.name for c in path)
        if not command.subcommands:
            return (" ".join([prefix, *(arg.usage for arg in command.args)]),)
        lines = [prefix] if command.run is not None else []
        for sub in command.subcommands:
            lines += self.usages([*path, sub])
        return tuple(lines)

    def usage_error(self, problem: str, path: Sequence[Command]) -> str:
        """Return an error message with the usage and a pointer to the help."""
        prefix = "/" + " ".join(c.name for c in path)
        usages = self.usages(path)
        usage = [f"Usage: {line}" for line in usages] if len(usages) <= 4 else []
        return "\n".join([problem, *usage, f"Type {prefix} help to learn more."])

    def _unknown(self, name: str) -> str:
        close = difflib.get_close_matches(name.lower(), self.names, n=1)
        problem = f"there's no /{name} command."
        if close:
            problem += f" Did you mean /{close[0]}?"
        return f"{problem} Type /help to see the commands."

    def _sub_names(self, command: Command) -> tuple[str, ...]:
        return tuple(sub.name for sub in command.subcommands)


def _missing(arg: Arg, options: Sequence[str]) -> str:
    """Say that a required argument is missing, with its options when it has some."""
    problem = f"it needs a value for <{arg.name}>"
    if 0 < len(options) <= 12:
        return f"{problem}, one of: {', '.join(options)}"
    if len(options) > 12:
        return f"{problem}, such as {options[0]} or {options[1]}"
    return problem


def _skip(text: str, position: int) -> tuple[int, str]:
    """Skip the spaces at `position`, and return where the next word starts and the rest."""
    rest = text[position:]
    stripped = rest.lstrip()
    return position + len(rest) - len(stripped), stripped
