"""The `/` commands, with no UI code."""

import shlex
from dataclasses import dataclass
from typing import get_args

from ironsworn_tui.campaign import Debility, Meter, ProgressTrack
from ironsworn_tui.rules.datasworn import Datasworn
from ironsworn_tui.rules.oracles import Likelihood, ask_yes_no, roll_oracle
from ironsworn_tui.rules.progress import TRACK_TICKS, Rank
from ironsworn_tui.turn import MoveInputs, RollCard, TurnEngine, plain_text

LIKELIHOODS = {
    "almost certain": Likelihood.ALMOST_CERTAIN,
    "likely": Likelihood.LIKELY,
    "50/50": Likelihood.FIFTY_FIFTY,
    "unlikely": Likelihood.UNLIKELY,
    "small chance": Likelihood.SMALL_CHANCE,
}
RANKS = {rank.name.lower(): rank for rank in Rank}
METERS: dict[str, Meter] = {"health": "health", "spirit": "spirit", "supply": "supply"}
DEBILITIES: dict[str, Debility] = {name: name for name in get_args(Debility.__value__)}
COMMANDS = ("oracle", "ask", "vow", "scene", "target", "tide", "adjust", "moves")


class CommandError(ValueError):
    """The command or its arguments aren't valid."""


@dataclass(frozen=True)
class CommandResult:
    """What a command did.

    Every command logs what it changes to the campaign log itself.

    Attributes:
        lines: Lines to show that aren't in the campaign log, such as the vow list.
        card: A roll card, when the command made a move (`/vow swear` or `/vow fulfill`).
        show_moves: True when the suggestion bar should show the full move list.
    """

    lines: tuple[str, ...] = ()
    card: RollCard | None = None
    show_moves: bool = False


def parse_rank(text: str) -> Rank:
    """Return the rank a word names, such as `dangerous`.

    Raises:
        CommandError: If the word isn't a rank.
    """
    try:
        return RANKS[text.strip().lower()]
    except KeyError:
        raise CommandError(f"rank must be one of: {', '.join(RANKS)}") from None


def parse_foes(text: str) -> tuple[tuple[str, Rank], ...]:
    """Parse foes written as `Raider chief dangerous, Archer troublesome`.

    Raises:
        CommandError: If a foe has no name or no rank.
    """
    foes: list[tuple[str, Rank]] = []
    for part in text.split(","):
        words = part.split()
        if len(words) < 2:
            raise CommandError("write each foe as a name and a rank, such as Raider dangerous")
        foes.append((" ".join(words[:-1]), parse_rank(words[-1])))
    return tuple(foes)


def find_table(data: Datasworn, name: str) -> str:
    """Return the oracle table an id or a short name refers to, such as `action`.

    Raises:
        CommandError: If no table or more than one matches.
    """
    if name in data.oracles:
        return name
    matches = [table_id for table_id in data.oracles if table_id.endswith(f"/{name}")]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise CommandError(f"no oracle table named {name!r}")
    raise CommandError(f"{name!r} could be: {', '.join(sorted(matches))}")


def run_command(engine: TurnEngine, text: str) -> CommandResult:
    """Run a `/` command against the engine's campaign.

    Args:
        engine: The turn engine.
        text: The command, starting with `/`.

    Returns:
        What the command did.

    Raises:
        CommandError: If the command or its arguments aren't valid.
        TurnError: If the command makes a move that can't be made now.
    """
    name, _, rest = text.removeprefix("/").partition(" ")
    rest = rest.strip()
    match name:
        case "oracle":
            return _oracle(engine, rest)
        case "ask":
            return _ask(engine, rest)
        case "vow":
            return _vow(engine, rest)
        case "scene":
            if not rest:
                raise CommandError("usage: /scene <text>")
            engine.set_scene(rest)
            return CommandResult()
        case "target":
            if not rest:
                raise CommandError("usage: /target <foe>")
            engine.set_target(rest)
            return CommandResult()
        case "tide":
            if rest == "off":
                engine.disarm_tide()
            elif rest:
                raise CommandError("usage: /tide [off]")
            else:
                engine.arm_tide()
            return CommandResult()
        case "adjust":
            return _adjust(engine, rest)
        case "moves":
            return CommandResult(show_moves=True)
        case _:
            raise CommandError(f"commands: {', '.join('/' + c for c in COMMANDS)}")


def _oracle(engine: TurnEngine, rest: str) -> CommandResult:
    if not rest:
        raise CommandError("usage: /oracle <table>")
    table_id = find_table(engine.data, rest)
    result = roll_oracle(engine.data, table_id, engine.rng)
    lines = [f"Oracle {table_id}, {result.roll}: {plain_text(result.text)}"]
    lines += [f"  {sub.roll}: {plain_text(sub.text)}" for sub in result.subrolls]
    for line in lines:
        engine.campaign.add_log("outcome", line)
    engine.save()
    return CommandResult()


def _ask(engine: TurnEngine, rest: str) -> CommandResult:
    likelihood = LIKELIHOODS.get(rest.lower())
    if likelihood is None:
        raise CommandError(f"likelihood must be one of: {', '.join(LIKELIHOODS)}")
    answer = ask_yes_no(likelihood, engine.rng)
    line = f"Ask the Oracle ({rest}), {answer.roll}: {'yes' if answer.yes else 'no'}"
    if answer.match:
        line += ", match"
    engine.campaign.add_log("outcome", line)
    engine.save()
    return CommandResult()


def _vow(engine: TurnEngine, rest: str) -> CommandResult:
    campaign = engine.campaign
    action, _, args = rest.partition(" ")
    args = args.strip()
    match action:
        case "":
            lines = [
                f"{vow.name} ({vow.rank.name.lower()}): {vow.boxes}/10" for vow in campaign.vows
            ]
            return CommandResult(lines=tuple(lines) or ("No vows",))
        case "swear":
            rank_word, _, vow = args.partition(" ")
            if not vow:
                raise CommandError("usage: /vow swear <rank> <vow>")
            inputs = MoveInputs(vow=vow, rank=parse_rank(rank_word))
            return CommandResult(card=engine.make_move("swear_an_iron_vow", inputs=inputs))
        case "mark":
            vow = _named_vow(engine, args)
            vow.mark()
            line = f"Reach a Milestone: {vow.name} is at {vow.boxes}/10"
            campaign.add_log("outcome", line)
            engine.save()
            return CommandResult()
        case "fulfill":
            inputs = MoveInputs(vow=_named_vow(engine, args).name)
            return CommandResult(card=engine.make_move("fulfill_your_vow", inputs=inputs))
        case "forsake":
            inputs = MoveInputs(vow=_named_vow(engine, args).name)
            engine.make_move("forsake_your_vow", inputs=inputs)
            return CommandResult()
        case _:
            raise CommandError("usage: /vow [swear <rank> <vow> | mark | fulfill | forsake <vow>]")


def _named_vow(engine: TurnEngine, name: str) -> ProgressTrack:
    vows = engine.campaign.vows
    if not name:
        if len(vows) == 1:
            return vows[0]
        raise CommandError("name the vow")
    try:
        return engine.campaign.vow(name)
    except KeyError as error:
        raise CommandError(str(error)) from error


def _amount(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise CommandError(f"{text!r} isn't a number") from None


def _adjust(engine: TurnEngine, rest: str) -> CommandResult:
    campaign = engine.campaign
    character = campaign.character
    try:
        words = shlex.split(rest)
    except ValueError as error:
        raise CommandError(str(error)) from error
    usage = (
        "usage: /adjust health|spirit|supply|momentum|experience|bonds <n>, "
        "<debility> mark|clear, vow|foe <name> <ticks>, journey <ticks>, harm 1|2, fight end"
    )
    if len(words) < 2:
        raise CommandError(usage)
    what, args = words[0], words[1:]
    if what in METERS and len(args) == 1:
        meter = METERS[what]
        changed = character.change_meter(meter, _amount(args[0]))
        line = f"{what.capitalize()} {changed:+d}, now {character.meter(meter)}"
    elif what == "momentum" and len(args) == 1:
        character.change_momentum(_amount(args[0]))
        line = f"Momentum is now {character.momentum}"
    elif what == "experience" and len(args) == 1:
        character.experience = max(0, character.experience + _amount(args[0]))
        line = f"Experience is now {character.experience}"
    elif what == "bonds" and len(args) == 1:
        campaign.bonds = max(0, min(TRACK_TICKS, campaign.bonds + _amount(args[0])))
        line = f"Bonds are now {campaign.bonds} ticks"
    elif what in DEBILITIES and args in (["mark"], ["clear"]):
        if args[0] == "mark":
            character.mark_debility(DEBILITIES[what])
        else:
            character.clear_debility(DEBILITIES[what])
        line = f"{what.capitalize()}: {'marked' if args[0] == 'mark' else 'cleared'}"
    elif what in ("vow", "foe") and len(args) >= 2:
        name = " ".join(args[:-1])
        tracks: list[ProgressTrack] = list(campaign.vows) if what == "vow" else list(campaign.foes)
        track = next((t for t in tracks if t.name == name), None)
        if track is None:
            raise CommandError(f"no {what} named {name!r}")
        track.ticks = max(0, min(TRACK_TICKS, track.ticks + _amount(args[-1])))
        line = f"{track.name} is now {track.ticks} ticks"
    elif what == "journey" and len(args) == 1:
        if campaign.journey is None:
            raise CommandError("there's no journey")
        journey = campaign.journey
        journey.ticks = max(0, min(TRACK_TICKS, journey.ticks + _amount(args[0])))
        line = f"{journey.name} is now {journey.ticks} ticks"
    elif what == "harm" and args in (["1"], ["2"]):
        character.harm = int(args[0])
        line = f"Harm is now {character.harm}"
    elif what == "fight" and args == ["end"]:
        engine.end_fight("by hand")
        return CommandResult()
    else:
        raise CommandError(usage)
    campaign.add_log("command", f"Adjust: {line}")
    engine.save()
    return CommandResult()
