"""The `/` commands, with no UI code."""

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, get_args

from ironsworn_tui.assets import (
    StatChanges,
    buy,
    change_asset_meter,
    discard,
    set_debility,
    set_field,
    upgrade,
)
from ironsworn_tui.campaign import (
    AssetError,
    Debility,
    Meter,
    NotFoundError,
    OwnedAsset,
    ProgressTrack,
    meter_max,
    setback_note,
)
from ironsworn_tui.rules.datasworn import Asset, Datasworn, Stat, plain_text
from ironsworn_tui.rules.oracles import Likelihood, ask_yes_no, roll_oracle
from ironsworn_tui.rules.progress import TRACK_TICKS, Rank
from ironsworn_tui.turn import MoveInputs, RollCard, TurnEngine, TurnError

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
STATS: dict[str, Stat] = {name: name for name in get_args(Stat.__value__)}
COMMANDS = (
    "oracle",
    "ask",
    "vow",
    "scene",
    "target",
    "tide",
    "adjust",
    "endure",
    "asset",
    "effects",
    "moves",
)
ASSET_USAGE = (
    "usage: /asset [list [category] | show <asset> | buy <asset> [ability [+stat -stat]] | "
    "upgrade <asset> <ability> [+stat -stat] | meter <asset> <meter> <n> | "
    "set <asset> <field> <value> | debility <asset> on|off | harm <companion> <n> | "
    "use lorekeeper | use slayer ritual|sojourn | discard <asset>]"
)


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


def find_asset(data: Datasworn, name: str, owned: Sequence[OwnedAsset] = ()) -> Asset:
    """Return the asset an id or a name refers to, such as `shadow_kin` or `Shadow-kin`.

    An owned companion also answers to the name set with `/asset set <companion> name
    <value>`. The catalog's ids and names come first, so `hawk` is always the Hawk asset.

    Args:
        data: The Datasworn data.
        name: The id, the name, or a companion's given name, in any case.
        owned: The character's assets, whose companions' given names also match.

    Raises:
        CommandError: If no asset matches.
    """
    key = name.strip().lower()
    for asset in data.assets.values():
        if key in (asset.id, asset.name.lower(), asset.id.replace("_", "-")):
            return asset
    for mine in owned:
        asset = data.asset(mine.id)
        if asset.category == "Companion" and mine.fields.get("name", "").lower() == key:
            return asset
    raise CommandError(f"no asset named {name!r}; /asset list shows them")


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
        case "endure":
            return _endure(engine, rest)
        case "asset":
            try:
                return _asset(engine, rest)
            except AssetError as error:
                raise CommandError(str(error)) from error
        case "effects":
            return _effects(engine, rest)
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
            engine.mark_vow(_named_vow(engine, args).name)
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
    except NotFoundError as error:
        raise CommandError(str(error)) from error


def _amount(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise CommandError(f"{text!r} isn't a number") from None


def _endure(engine: TurnEngine, rest: str) -> CommandResult:
    match rest.split():
        case ["harm" | "stress" as what, amount]:
            move: Literal["endure_harm", "endure_stress"] = (
                "endure_harm" if what == "harm" else "endure_stress"
            )
            try:
                engine.endure(move, _amount(amount))
            except TurnError as error:
                raise CommandError(str(error)) from error
            return CommandResult()
        case _:
            raise CommandError("usage: /endure harm|stress <n>")


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
    setback = 0
    if what in METERS and len(args) == 1:
        meter = METERS[what]
        changed = character.change_meter(meter, _amount(args[0]))
        line = f"{what.capitalize()} {changed:+d}, now {character.meter(meter)}"
    elif what == "momentum" and len(args) == 1:
        setback = character.change_momentum(_amount(args[0]))
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
    if setback:
        campaign.add_log("note", setback_note(setback))
    engine.expire_low()
    engine.save()
    return CommandResult()


def asset_summary(data: Datasworn, owned: OwnedAsset) -> str:
    """Describe an owned asset in one line: its name, marked abilities, and meters.

    For example, `Hawk (Kestrel): 2, health 3/3`.
    """
    asset = data.asset(owned.id)
    name = asset.name
    if "name" in owned.fields:
        name += f" ({owned.fields['name']})"
    parts = [", ".join(str(n) for n, mark in enumerate(owned.marked, 1) if mark)]
    parts += [
        f"{meter} {value}/{meter_max(data, owned, meter)}" for meter, value in owned.meters.items()
    ]
    parts += [f"{field} {value}" for field, value in owned.fields.items() if field != "name"]
    return f"{name}: {', '.join(parts)}"


def _asset(engine: TurnEngine, rest: str) -> CommandResult:
    data = engine.data
    character = engine.campaign.character
    words = rest.split()
    if not words:
        return CommandResult(tuple(asset_summary(data, owned) for owned in character.assets))
    action, args = words[0], words[1:]
    if action == "list" and len(args) <= 1:
        category = args[0].replace("_", " ").lower() if args else None
        assets = [a for a in data.assets.values() if category in (None, a.category.lower())]
        if not assets:
            raise CommandError("categories: combat_talent, companion, path, ritual")
        return CommandResult(tuple(f"{a.id}: {a.name}" for a in assets))
    if not args:
        raise CommandError(ASSET_USAGE)
    asset, args = _split_asset(data, args, character.assets)
    if action == "show" and len(args) == 1:
        return CommandResult(_asset_card(engine, asset))
    match action:
        case "buy":
            ability = _ability(args[1]) if len(args) > 1 else None
            spent = buy(character, data, asset.id, ability, _changes(args[2:]))
            line = f"bought {asset.name} for {spent} experience"
        case "upgrade" if len(args) >= 2:
            ability = _ability(args[1])
            spent = upgrade(character, data, asset.id, ability, _changes(args[2:]))
            line = f"marked {asset.name}'s ability {ability} for {spent} experience"
        case "meter" if len(args) == 3:
            meter = args[1]
            changed = change_asset_meter(character, data, asset.id, meter, _amount(args[2]))
            now = character.asset(asset.id).meters[meter]
            line = f"{asset.name} {meter} {changed:+d}, now {now}"
        case "set" if len(args) >= 3:
            value = " ".join(args[2:])
            set_field(character, data, asset.id, args[1], value)
            line = f"{asset.name} {args[1]} is now {value}"
        case "harm" if len(args) == 2:
            try:
                engine.harm_companion(asset.id, _amount(args[1]))
            except TurnError as error:
                raise CommandError(str(error)) from error
            return CommandResult()
        case "use" if asset.id == "lorekeeper" and len(args) == 1:
            try:
                engine.browse_archive()
            except TurnError as error:
                raise CommandError(str(error)) from error
            return CommandResult()
        case "use" if asset.id == "slayer" and args[1:] in (["ritual"], ["sojourn"]):
            try:
                engine.take_trophy("ritual" if args[1] == "ritual" else "sojourn")
            except TurnError as error:
                raise CommandError(str(error)) from error
            return CommandResult()
        case "debility" if args[1:] in (["on"], ["off"]):
            on = args[1] == "on"
            set_debility(character, asset.id, on=on)
            line = f"{asset.name} {'counts' if on else 'no longer counts'} as a debility"
        case "discard" if len(args) == 1:
            discard(character, asset.id)
            line = f"discarded {asset.name}"
        case _:
            raise CommandError(ASSET_USAGE)
    engine.campaign.add_log("command", f"Asset: {line}")
    engine.save()
    return CommandResult()


def _split_asset(
    data: Datasworn, words: list[str], owned: Sequence[OwnedAsset]
) -> tuple[Asset, list[str]]:
    """Find the asset the leading words name, trying the longest run first.

    Returns:
        The asset, and the words with the name replaced by the asset id.
    """
    for end in range(len(words), 0, -1):
        try:
            asset = find_asset(data, " ".join(words[:end]), owned)
        except CommandError:
            continue
        return asset, [asset.id, *words[end:]]
    raise CommandError(f"no asset named {words[0]!r}; /asset list shows them")


def _asset_card(engine: TurnEngine, asset: Asset) -> tuple[str, ...]:
    owned = engine.campaign.character.asset_or_none(asset.id)
    head = f"{asset.name} ({asset.category.lower()})."
    if asset.requirement:
        head += f" {asset.requirement}"
    lines = [head]
    for number, ability in enumerate(asset.abilities, 1):
        mark = "[x]" if owned is not None and owned.marked[number - 1] else "[ ]"
        text = " ".join(ability.text.split())
        lines.append(f"{mark} {number}. {text}")
    if owned is not None:
        lines.append(asset_summary(engine.data, owned))
    return tuple(lines)


def _ability(text: str) -> int:
    if not text.isdigit():
        raise CommandError(ASSET_USAGE)
    return int(text)


def _is_change(word: str) -> bool:
    return word[:1] in "+-"


def _changes(words: list[str]) -> StatChanges:
    changes: StatChanges = {}
    for word in words:
        stat = STATS.get(word[1:].lower())
        if not _is_change(word) or stat is None:
            raise CommandError(
                f"write a stat change as +stat or -stat, such as +wits, not {word!r}"
            )
        changes[stat] = changes.get(stat, 0) + (1 if word[0] == "+" else -1)
    return changes


def _effects(engine: TurnEngine, rest: str) -> CommandResult:
    words = rest.split()
    if not words:
        labels = engine.lasting_labels()
        lines = [f"{number} {label}" for number, label in enumerate(labels, 1)]
        return CommandResult(tuple(lines) or ("No lasting effects",))
    if words[0] == "end" and len(words) == 2 and words[1].isdigit():
        try:
            engine.end_lasting(int(words[1]) - 1)
        except TurnError as error:
            raise CommandError(str(error)) from error
        return CommandResult()
    raise CommandError("usage: /effects [end <number>]")
