"""The `/` commands and their registry, with no UI code."""

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
from ironsworn_tui.registry import (
    Arg,
    Command,
    CommandError,
    CommandResult,
    Registry,
    UsageError,
    Values,
)
from ironsworn_tui.rules.datasworn import Asset, Datasworn, Stat, plain_text
from ironsworn_tui.rules.oracles import Likelihood, ask_yes_no, roll_oracle
from ironsworn_tui.rules.progress import TICKS_PER_BOX, TRACK_TICKS, Rank
from ironsworn_tui.turn import MoveInputs, TurnEngine, TurnError, progress_text

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
STAT_CHANGES = tuple(f"{sign}{stat}" for stat in STATS for sign in "+-")
CATEGORIES = ("combat_talent", "companion", "path", "ritual")
USABLE = ("lorekeeper", "slayer")


@dataclass(frozen=True)
class OracleEntry:
    """An oracle table under a short name.

    Attributes:
        name: The short name `/oracle` takes, such as `action`.
        tables: The table ids. With more than one, a roll picks one of them, as the rulebook
            says for Ironlander names.
        summary: What the table gives, for the help.
    """

    name: str
    tables: tuple[str, ...]
    summary: str


def _entry(name: str, table: str, summary: str) -> OracleEntry:
    return OracleEntry(name, (f"classic/{table}",), summary)


ORACLE_GROUPS: tuple[tuple[str, tuple[OracleEntry, ...]], ...] = (
    (
        "Spark an idea",
        (
            _entry("action", "action_and_theme/action", "a verb, such as Clash or Scheme"),
            _entry("theme", "action_and_theme/theme", "a noun, such as Risk or Ally"),
        ),
    ),
    (
        "Characters",
        (
            _entry("role", "character/role", "who they are, such as Healer"),
            _entry("goal", "character/goal", "what they want, such as Obtain an object"),
            _entry("descriptor", "character/descriptor", "what they're like, such as Stoic"),
        ),
    ),
    (
        "Names",
        (
            OracleEntry(
                "ironlander-name",
                ("classic/name/ironlander/a", "classic/name/ironlander/b"),
                "a name for one of the people of the Ironlands",
            ),
            _entry("elf-name", "name/elf", "a name for an elf"),
            _entry("giant-name", "name/other/giants", "a name for a giant"),
            _entry("varou-name", "name/other/varou", "a name for a varou"),
            _entry("troll-name", "name/other/trolls", "a name for a troll"),
        ),
    ),
    (
        "Places",
        (
            _entry("region", "place/region", "a region of the Ironlands, such as Deep Wilds"),
            _entry("location", "place/location", "a place, such as Ruin or Mine"),
            _entry(
                "coastal-location",
                "place/coastal_waters_location",
                "a place on the water, such as Fleet",
            ),
            _entry("place-descriptor", "place/descriptor", "what a place is like, such as Remote"),
        ),
    ),
    (
        "Settlements",
        (
            _entry(
                "settlement-name",
                "settlement/name",
                "where a settlement's name comes from, with an example",
            ),
            _entry(
                "quick-name-prefix",
                "settlement/quick_name/prefix",
                "the first half of a name, such as Raven",
            ),
            _entry(
                "quick-name-suffix",
                "settlement/quick_name/suffix",
                "the second half of a name, such as ford",
            ),
            _entry(
                "settlement-trouble",
                "settlement/trouble",
                "a settlement's problem, such as Dreadful omens",
            ),
        ),
    ),
    (
        "Turning points",
        (
            _entry(
                "plot-twist",
                "turning_point/major_plot_twist",
                "a surprise, such as A trap is sprung",
            ),
            _entry(
                "combat-action", "turning_point/combat_action", "what a foe does next in a fight"
            ),
            _entry(
                "mystic-backlash",
                "turning_point/mystic_backlash",
                "what goes wrong when a ritual fails",
            ),
            _entry(
                "challenge-rank",
                "turning_point/challenge_rank",
                "how hard a foe or a vow is, from Troublesome to Epic",
            ),
        ),
    ),
    (
        "Fate",
        (
            _entry(
                "pay-the-price",
                "fate/pay_the_price/pay_the_price",
                "a cost or complication, as after a miss",
            ),
        ),
    ),
)
ORACLES = {entry.name: entry for _, entries in ORACLE_GROUPS for entry in entries}


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
        What the command did, or its help.

    Raises:
        CommandError: If the command or its arguments aren't valid.
        TurnError: If the command makes a move that can't be made now.
    """
    parsed = REGISTRY.parse(engine, text)
    if parsed.help:
        return CommandResult(help=REGISTRY.help(parsed.path))
    run = parsed.path[-1].run
    assert run is not None, "the registry parses only to commands that run"
    try:
        return run(engine, parsed.values)
    except UsageError as error:
        raise CommandError(REGISTRY.usage_error(str(error), parsed.path)) from None
    except AssetError as error:
        raise CommandError(str(error)) from error


def changes_nothing(engine: TurnEngine, text: str) -> bool:
    """Return True when a command only shows help or quits, so it can run while a roll waits.

    Args:
        engine: The turn engine.
        text: The command, starting with `/`.
    """
    try:
        parsed = REGISTRY.parse(engine, text)
    except CommandError:
        return False
    return parsed.help or parsed.path[0].name in ("help", "quit")


# The options each argument offers.


def _vow_names(engine: TurnEngine, _: Values) -> list[str]:
    return [vow.name for vow in engine.campaign.vows]


def _foe_names(engine: TurnEngine, _: Values) -> list[str]:
    return [foe.name for foe in engine.campaign.foes]


def _given_names(engine: TurnEngine, assets: Sequence[OwnedAsset]) -> list[str]:
    data = engine.data
    return [
        mine.fields["name"]
        for mine in assets
        if data.asset(mine.id).category == "Companion" and mine.fields.get("name")
    ]


def _assets_where(
    engine: TurnEngine, keep: Literal["all", "meters", "fields", "companions"]
) -> list[str]:
    data = engine.data
    assets = [
        mine
        for mine in engine.campaign.character.assets
        if keep == "all"
        or (keep == "meters" and mine.meters)
        or (keep == "fields" and (data.asset(mine.id).texts or data.asset(mine.id).selects))
        or (keep == "companions" and data.asset(mine.id).category == "Companion")
    ]
    return [*(mine.id for mine in assets), *_given_names(engine, assets)]


def _catalog(engine: TurnEngine, _: Values) -> list[str]:
    return [*engine.data.assets, *_given_names(engine, engine.campaign.character.assets)]


def _owned(engine: TurnEngine, _: Values) -> list[str]:
    return _assets_where(engine, "all")


def _with_meters(engine: TurnEngine, _: Values) -> list[str]:
    return _assets_where(engine, "meters")


def _with_fields(engine: TurnEngine, _: Values) -> list[str]:
    return _assets_where(engine, "fields")


def _companions(engine: TurnEngine, _: Values) -> list[str]:
    return _assets_where(engine, "companions")


def _asset_of(engine: TurnEngine, name: str) -> Asset:
    return find_asset(engine.data, name, engine.campaign.character.assets)


def _unmarked(engine: TurnEngine, values: Values) -> list[str]:
    owned = engine.campaign.character.asset_or_none(_asset_of(engine, values[0]).id)
    if owned is None:
        return []
    return [str(number) for number, mark in enumerate(owned.marked, 1) if not mark]


def _asset_meters(engine: TurnEngine, values: Values) -> list[str]:
    return list(_asset_of(engine, values[0]).meters)


def _asset_fields(engine: TurnEngine, values: Values) -> list[str]:
    asset = _asset_of(engine, values[0])
    return [*asset.texts, *asset.selects]


def _field_choices(engine: TurnEngine, values: Values) -> list[str]:
    select = _asset_of(engine, values[0]).selects.get(values[1])
    return list(select.choices) if select is not None else []


def _uses(_: TurnEngine, values: Values) -> tuple[str, ...]:
    return ("ritual", "sojourn") if values[0] == "slayer" else ()


def _effect_numbers(engine: TurnEngine, _: Values) -> list[str]:
    return [str(number) for number in range(1, len(engine.campaign.lasting) + 1)]


def _command_names(_: TurnEngine, __: Values) -> tuple[str, ...]:
    return REGISTRY.names


# The commands.


def _help(_: TurnEngine, values: Values) -> CommandResult:
    if not values:
        return CommandResult(help=REGISTRY.overview())
    command = REGISTRY.find(values[0])
    assert command is not None, "the parser checks the command name"
    return CommandResult(help=REGISTRY.help([command]))


def _asked(name: str, values: Values) -> str:
    question = f"{values[1]} " if len(values) > 1 else ""
    return f"{name}: {question}"


def _oracle(engine: TurnEngine, values: Values) -> CommandResult:
    entry = ORACLES[values[0]]
    table_id = entry.tables[0]
    if len(entry.tables) > 1:
        table_id = entry.tables[engine.rng.randint(1, len(entry.tables)) - 1]
    result = roll_oracle(engine.data, table_id, engine.rng)
    head = _asked(f"Oracle ({entry.name})", values)
    lines = [f"{head}{result.roll}: {plain_text(result.text)}"]
    lines += [f"  {sub.roll}: {plain_text(sub.text)}" for sub in result.subrolls]
    for line in lines:
        engine.campaign.add_log("outcome", line)
    engine.save()
    return CommandResult()


def _ask(engine: TurnEngine, values: Values) -> CommandResult:
    likelihood = values[0]
    answer = ask_yes_no(LIKELIHOODS[likelihood], engine.rng)
    head = _asked(f"Ask ({likelihood})", values)
    line = f"{head}{answer.roll}: {'yes' if answer.yes else 'no'}"
    if answer.match:
        line += ", match"
    engine.campaign.add_log("outcome", line)
    engine.save()
    return CommandResult()


def _note(engine: TurnEngine, values: Values) -> CommandResult:
    engine.campaign.add_log("player_note", values[0])
    engine.save()
    return CommandResult()


def _vows(engine: TurnEngine, _: Values) -> CommandResult:
    vows = engine.campaign.vows
    lines = [f"{vow.name} ({vow.rank.name.lower()}): {_filled(vow)}" for vow in vows]
    return CommandResult(lines=tuple(lines) or ("No vows",))


def _filled(track: ProgressTrack) -> str:
    """Show a track's progress, such as `2/10 boxes, 1 tick`."""
    ticks = track.ticks % TICKS_PER_BOX
    extra = f", {progress_text(ticks)}" if ticks else ""
    return f"{track.boxes}/10 boxes{extra}"


def _vow_swear(engine: TurnEngine, values: Values) -> CommandResult:
    inputs = MoveInputs(vow=values[1], rank=RANKS[values[0]])
    return CommandResult(card=engine.make_move("swear_an_iron_vow", inputs=inputs))


def _vow_mark(engine: TurnEngine, values: Values) -> CommandResult:
    engine.mark_vow(_named_vow(engine, values).name)
    return CommandResult()


def _vow_fulfill(engine: TurnEngine, values: Values) -> CommandResult:
    inputs = MoveInputs(vow=_named_vow(engine, values).name)
    return CommandResult(card=engine.make_move("fulfill_your_vow", inputs=inputs))


def _vow_forsake(engine: TurnEngine, values: Values) -> CommandResult:
    engine.make_move("forsake_your_vow", inputs=MoveInputs(vow=_named_vow(engine, values).name))
    return CommandResult()


def _named_vow(engine: TurnEngine, values: Values) -> ProgressTrack:
    vows = engine.campaign.vows
    if not values:
        if len(vows) == 1:
            return vows[0]
        raise UsageError("name the vow" if vows else "there are no vows")
    try:
        return engine.campaign.vow(values[0])
    except NotFoundError as error:
        raise CommandError(str(error)) from error


def _scene(engine: TurnEngine, values: Values) -> CommandResult:
    engine.set_scene(values[0])
    return CommandResult()


def _target(engine: TurnEngine, values: Values) -> CommandResult:
    engine.set_target(values[0])
    return CommandResult()


def _tide(engine: TurnEngine, values: Values) -> CommandResult:
    if values:
        engine.disarm_tide()
    else:
        engine.arm_tide()
    return CommandResult()


def _adjusted(engine: TurnEngine, line: str, setback: int = 0) -> CommandResult:
    campaign = engine.campaign
    campaign.add_log("command", f"Adjust: {line}")
    if setback:
        campaign.add_log("note", setback_note(setback))
    engine.expire_low()
    engine.save()
    return CommandResult()


def _adjust_meter(meter: Meter) -> Command:
    def run(engine: TurnEngine, values: Values) -> CommandResult:
        character = engine.campaign.character
        changed = character.change_meter(meter, int(values[0]))
        return _adjusted(engine, f"{meter.capitalize()} {changed:+d}, now {character.meter(meter)}")

    return Command(
        meter,
        f"Add to or take from {meter}, from 0 to 5",
        run,
        (Arg("n", number=True),),
        examples=(f"/adjust {meter} -1",),
    )


def _adjust_momentum(engine: TurnEngine, values: Values) -> CommandResult:
    character = engine.campaign.character
    setback = character.change_momentum(int(values[0]))
    return _adjusted(engine, f"Momentum is now {character.momentum}", setback)


def _adjust_experience(engine: TurnEngine, values: Values) -> CommandResult:
    character = engine.campaign.character
    character.experience = max(0, character.experience + int(values[0]))
    return _adjusted(engine, f"Experience is now {character.experience}")


def _adjust_bonds(engine: TurnEngine, values: Values) -> CommandResult:
    campaign = engine.campaign
    campaign.bonds = max(0, min(TRACK_TICKS, campaign.bonds + int(values[0])))
    return _adjusted(engine, f"Bonds are now {campaign.bonds} ticks")


def _adjust_debility(debility: Debility) -> Command:
    def run(engine: TurnEngine, values: Values) -> CommandResult:
        character = engine.campaign.character
        if values[0] == "mark":
            character.mark_debility(debility)
        else:
            character.clear_debility(debility)
        done = "marked" if values[0] == "mark" else "cleared"
        return _adjusted(engine, f"{debility.capitalize()}: {done}")

    return Command(
        debility,
        f"Mark or clear the {debility} debility",
        run,
        (Arg("change", ("mark", "clear")),),
        examples=(f"/adjust {debility} mark",),
    )


def _adjust_track(kind: Literal["vow", "foe"]) -> Command:
    def run(engine: TurnEngine, values: Values) -> CommandResult:
        campaign = engine.campaign
        tracks: list[ProgressTrack] = list(campaign.vows if kind == "vow" else campaign.foes)
        track = next(t for t in tracks if t.name == values[0])
        track.ticks = max(0, min(TRACK_TICKS, track.ticks + int(values[1])))
        return _adjusted(engine, f"{track.name} is now {track.ticks} ticks")

    example = "Find my brother" if kind == "vow" else "Raider"
    return Command(
        kind,
        f"Add ticks to a {kind}'s progress track, 4 to a box",
        run,
        (Arg(kind, _vow_names if kind == "vow" else _foe_names), Arg("ticks", number=True)),
        examples=(f"/adjust {kind} {example} 4",),
    )


def _adjust_journey(engine: TurnEngine, values: Values) -> CommandResult:
    journey = engine.campaign.journey
    if journey is None:
        raise CommandError("there's no journey")
    journey.ticks = max(0, min(TRACK_TICKS, journey.ticks + int(values[0])))
    return _adjusted(engine, f"{journey.name} is now {journey.ticks} ticks")


def _adjust_harm(engine: TurnEngine, values: Values) -> CommandResult:
    character = engine.campaign.character
    character.harm = int(values[0])
    return _adjusted(engine, f"Harm is now {character.harm}")


def _adjust_fight(engine: TurnEngine, _: Values) -> CommandResult:
    engine.end_fight("by hand")
    return CommandResult()


def _endure(move: Literal["endure_harm", "endure_stress"]) -> Command:
    def run(engine: TurnEngine, values: Values) -> CommandResult:
        try:
            engine.endure(move, int(values[0]) if values else None)
        except TurnError as error:
            raise CommandError(str(error)) from error
        return CommandResult()

    if move == "endure_harm":
        return Command(
            "harm",
            "Owe Endure Harm when your character is hurt",
            run,
            (Arg("n", number=True, optional=True),),
            help=(
                "Use it when something hurts your character and no move asked for the roll, "
                "such as a foe's blow or a fall. Leave out the number in a fight to take the "
                "targeted foe's harm.",
            ),
            examples=("/endure harm 2",),
        )
    return Command(
        "stress",
        "Owe Endure Stress when your character is shaken",
        run,
        (Arg("n", number=True),),
        help=(
            "Use it when something frightens, saddens, or wears down your character, such as "
            "a horror or a loss.",
        ),
        examples=("/endure stress 1",),
    )


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


def _assets(engine: TurnEngine, _: Values) -> CommandResult:
    character = engine.campaign.character
    return CommandResult(tuple(asset_summary(engine.data, owned) for owned in character.assets))


def _asset_list(engine: TurnEngine, values: Values) -> CommandResult:
    category = values[0].replace("_", " ") if values else None
    assets = [a for a in engine.data.assets.values() if category in (None, a.category.lower())]
    return CommandResult(tuple(f"{a.id}: {a.name}" for a in assets))


def _asset_show(engine: TurnEngine, values: Values) -> CommandResult:
    asset = _asset_of(engine, values[0])
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
    return CommandResult(tuple(lines))


def _asset_logged(engine: TurnEngine, line: str) -> CommandResult:
    engine.campaign.add_log("command", f"Asset: {line}")
    engine.save()
    return CommandResult()


def _changes(words: Sequence[str]) -> StatChanges:
    changes: StatChanges = {}
    for word in words:
        stat = STATS[word[1:]]
        changes[stat] = changes.get(stat, 0) + (1 if word[0] == "+" else -1)
    return changes


def _asset_buy(engine: TurnEngine, values: Values) -> CommandResult:
    asset = _asset_of(engine, values[0])
    ability = int(values[1]) if len(values) > 1 else None
    spent = buy(engine.campaign.character, engine.data, asset.id, ability, _changes(values[2:]))
    return _asset_logged(engine, f"bought {asset.name} for {spent} experience")


def _asset_upgrade(engine: TurnEngine, values: Values) -> CommandResult:
    asset = _asset_of(engine, values[0])
    ability = int(values[1])
    character = engine.campaign.character
    spent = upgrade(character, engine.data, asset.id, ability, _changes(values[2:]))
    return _asset_logged(engine, f"marked {asset.name}'s ability {ability} for {spent} experience")


def _asset_meter(engine: TurnEngine, values: Values) -> CommandResult:
    asset = _asset_of(engine, values[0])
    meter = values[1]
    character = engine.campaign.character
    changed = change_asset_meter(character, engine.data, asset.id, meter, int(values[2]))
    now = character.asset(asset.id).meters[meter]
    return _asset_logged(engine, f"{asset.name} {meter} {changed:+d}, now {now}")


def _asset_set(engine: TurnEngine, values: Values) -> CommandResult:
    asset = _asset_of(engine, values[0])
    field, value = values[1], values[2]
    set_field(engine.campaign.character, engine.data, asset.id, field, value)
    return _asset_logged(engine, f"{asset.name} {field} is now {value}")


def _asset_debility(engine: TurnEngine, values: Values) -> CommandResult:
    asset = _asset_of(engine, values[0])
    on = values[1] == "on"
    set_debility(engine.campaign.character, asset.id, on=on)
    counts = "counts" if on else "no longer counts"
    return _asset_logged(engine, f"{asset.name} {counts} as a debility")


def _asset_harm(engine: TurnEngine, values: Values) -> CommandResult:
    asset = _asset_of(engine, values[0])
    try:
        engine.harm_companion(asset.id, int(values[1]))
    except TurnError as error:
        raise CommandError(str(error)) from error
    return CommandResult()


def _asset_use(engine: TurnEngine, values: Values) -> CommandResult:
    if values[0] == "slayer" and len(values) < 2:
        raise UsageError("Slayer's trophy is for a ritual or a sojourn")
    try:
        if values[0] == "lorekeeper":
            engine.browse_archive()
        else:
            engine.take_trophy("ritual" if values[1] == "ritual" else "sojourn")
    except TurnError as error:
        raise CommandError(str(error)) from error
    return CommandResult()


def _asset_discard(engine: TurnEngine, values: Values) -> CommandResult:
    asset = _asset_of(engine, values[0])
    discard(engine.campaign.character, asset.id)
    return _asset_logged(engine, f"discarded {asset.name}")


def _effects(engine: TurnEngine, _: Values) -> CommandResult:
    labels = engine.lasting_labels()
    lines = [f"{number} {label}" for number, label in enumerate(labels, 1)]
    return CommandResult(tuple(lines) or ("No lasting effects",))


def _effects_end(engine: TurnEngine, values: Values) -> CommandResult:
    try:
        engine.end_lasting(int(values[0]) - 1)
    except TurnError as error:
        raise CommandError(str(error)) from error
    return CommandResult()


def _quit(_: TurnEngine, __: Values) -> CommandResult:
    return CommandResult(quit=True)


def _moves(_: TurnEngine, __: Values) -> CommandResult:
    return CommandResult(show_moves=True)


def _oracle_tables() -> tuple[str, ...]:
    lines = ["Tables:"]
    for group, entries in ORACLE_GROUPS:
        lines.append(f"  {group}: {', '.join(entry.name for entry in entries)}")
    lines.append("What each table gives:")
    lines += [f"  {entry.name}: {entry.summary}" for entry in ORACLES.values()]
    return tuple(lines)


_QUESTION = Arg("question", free=True, rest=True, optional=True)
_VOW = Arg("vow", _vow_names, optional=True)
_OWNED = Arg("asset", _owned)

REGISTRY = Registry(
    (
        Command(
            "help",
            "List the commands, or explain one",
            _help,
            (Arg("command", _command_names, optional=True),),
            help=(
                "Every command has its own help. Type help after the command, such as "
                "/oracle help, or name the command here.",
            ),
            examples=("/help", "/help vow"),
        ),
        Command(
            "moves",
            "Show every move you can make, to pick one by hand",
            _moves,
            help=(
                "A move is a rule for a risky or important action, such as Face Danger or "
                "Strike. Usually you describe what your character does, and the app suggests "
                "the move. Use /moves when you already know the move you want, or the "
                "suggestion isn't right. The moves appear in the bar below the log. Pick one "
                "with its key or the arrows. If the bar asks for a stat, press its key. Then "
                "press Enter to roll.",
            ),
            examples=("/moves",),
        ),
        Command(
            "oracle",
            "Roll on an oracle table for a name, a place, or an idea",
            _oracle,
            (Arg("table", tuple(ORACLES)), _QUESTION),
            help=(
                "In solo play there's no game master to tell you what's out there. Oracles "
                "fill that role. Each oracle is a table of random answers that you read in "
                "the light of your story.",
                "Roll one when you need a name, want to know what a place is like, or have "
                "no idea what happens next. If the answer doesn't fit, read it loosely, or "
                "roll again. For a yes or no question, use /ask instead.",
                "action and theme work as a pair: roll both and read them together, such as "
                "Clash and Ally.",
                "Write your question after the table, and the log keeps it with the answer, "
                "such as /oracle location Do I know which castle I'm in?",
            ),
            examples=("/oracle action", "/oracle ironlander-name What is the guard called?"),
            extra=_oracle_tables(),
        ),
        Command(
            "ask",
            "Ask the oracle a yes or no question",
            _ask,
            (Arg("likelihood", tuple(LIKELIHOODS)), _QUESTION),
            help=(
                "Think of a yes or no question about the world, such as Is the bridge "
                "guarded? Decide how likely a yes is, and roll. The app rolls 1 to 100.",
                "The answer is yes on: almost certain 11 or more, likely 26 or more, 50/50 51 "
                "or more, unlikely 76 or more, small chance 91 or more.",
                "Doubles, such as 22 or 77, are a match. A match means something extreme or "
                "a twist: a yes is a big yes, and a no can be a nasty surprise.",
                "To choose between two ideas, rate one as likely and ask. If the answer is "
                "no, it's the other one.",
                "Write your question after the likelihood, and the log keeps it with the "
                "answer, such as /ask almost certain Do I know which castle I'm in?",
            ),
            examples=("/ask likely", "/ask almost certain Do I know which castle I'm in?"),
        ),
        Command(
            "note",
            "Write a note in the log, such as a clue, a name, or a question",
            _note,
            (Arg("text", free=True, rest=True),),
            help=(
                "The note is saved in the campaign log, so it's there when you come back. "
                "It changes nothing else.",
            ),
            examples=("/note The ferryman is named Oda",),
        ),
        Command(
            "vow",
            "List your vows, or swear, mark, fulfill, or forsake one",
            _vows,
            subcommands=(
                Command(
                    "swear",
                    "Swear a new iron vow, a quest your character commits to",
                    _vow_swear,
                    (Arg("rank", tuple(RANKS)), Arg("vow", free=True, rest=True)),
                    help=(
                        "The rank says how long and hard the quest is: troublesome is a "
                        "short task, and epic can take a whole campaign. Swearing rolls the "
                        "Swear an Iron Vow move.",
                    ),
                    examples=("/vow swear dangerous Find my brother",),
                ),
                Command(
                    "mark",
                    "Mark progress on a vow when you reach a milestone",
                    _vow_mark,
                    (_VOW,),
                    help=(
                        "A milestone is a real step toward the vow, such as finding a clue "
                        "or reaching a place. Higher ranks mark less progress each time. You "
                        "can leave out the name when you have one vow.",
                    ),
                    examples=("/vow mark Find my brother",),
                ),
                Command(
                    "fulfill",
                    "Try to complete a vow with a progress roll",
                    _vow_fulfill,
                    (_VOW,),
                    help=(
                        "Use it when the story reaches the vow's end. The more progress "
                        "you marked, the better your chances. Fulfilling a vow earns "
                        "experience.",
                    ),
                    examples=("/vow fulfill Find my brother",),
                ),
                Command(
                    "forsake",
                    "Give up on a vow",
                    _vow_forsake,
                    (_VOW,),
                    help=("Breaking a vow hurts: the vow is cleared, and you owe Endure Stress.",),
                    examples=("/vow forsake Find my brother",),
                ),
            ),
            help=(
                "Vows drive an Ironsworn story. Each vow is a quest with a rank and a "
                "progress track of 10 boxes. Swear a vow, mark progress as you reach "
                "milestones, then try to fulfill it.",
                "With no option, /vow lists your vows and their progress.",
            ),
            examples=("/vow", "/vow swear dangerous Find my brother"),
        ),
        Command(
            "scene",
            "Describe where your character is and what's around them",
            _scene,
            (Arg("text", free=True, rest=True),),
            help=(
                "The scene helps the app suggest the right move for what you type. Set a new "
                "one when your character arrives somewhere or the situation changes.",
            ),
            examples=("/scene A ruined watchtower in the rain",),
        ),
        Command(
            "target",
            "Pick the foe your attacks hit in a fight",
            _target,
            (Arg("foe", _foe_names),),
            help=("Without a pick, attacks hit the first foe in the fight.",),
            examples=("/target Raider chief",),
        ),
        Command(
            "tide",
            "Turn the Tide once a fight, when the foe has the upper hand",
            _tide,
            (Arg("off", ("off",), optional=True),),
            help=(
                "Once a fight, when the foe has the initiative, you can risk it all and take "
                "the initiative back. /tide arms it for your next move, which adds 1 and "
                "gains 1 momentum on a hit. If that move misses, you Pay the Price. /tide off "
                "disarms it unused.",
            ),
            examples=("/tide", "/tide off"),
        ),
        Command(
            "adjust",
            "Change a value by hand, such as health or a vow's progress",
            subcommands=(
                *(_adjust_meter(meter) for meter in METERS.values()),
                Command(
                    "momentum",
                    "Add to or take from momentum",
                    _adjust_momentum,
                    (Arg("n", number=True),),
                    examples=("/adjust momentum +2",),
                ),
                Command(
                    "experience",
                    "Add to or take from experience",
                    _adjust_experience,
                    (Arg("n", number=True),),
                    examples=("/adjust experience 2",),
                ),
                Command(
                    "bonds",
                    "Add ticks to the bonds track, 4 to a box",
                    _adjust_bonds,
                    (Arg("ticks", number=True),),
                    examples=("/adjust bonds 4",),
                ),
                *(_adjust_debility(debility) for debility in DEBILITIES.values()),
                _adjust_track("vow"),
                _adjust_track("foe"),
                Command(
                    "journey",
                    "Add ticks to the journey's progress track, 4 to a box",
                    _adjust_journey,
                    (Arg("ticks", number=True),),
                    examples=("/adjust journey 4",),
                ),
                Command(
                    "harm",
                    "Set the harm your attacks deal: 2 with a deadly weapon, 1 without",
                    _adjust_harm,
                    (Arg("harm", ("1", "2"), number=True),),
                    examples=("/adjust harm 1",),
                ),
                Command(
                    "fight",
                    "End the fight without a move",
                    _adjust_fight,
                    (Arg("end", ("end",)),),
                    examples=("/adjust fight end",),
                ),
            ),
            help=(
                "Moves change your character's values for you. Use /adjust when the story "
                "changes one without a move, such as a meal that restores supply, or to fix "
                "a mistake.",
                "Health, spirit, and supply run from 0 to 5. Momentum runs from -6 to +10. "
                "A debility, such as wounded, is a lasting condition that lowers your "
                "momentum's maximum. A progress track has 10 boxes of 4 ticks each.",
            ),
            examples=("/adjust health -2", "/adjust wounded mark", "/adjust vow Find my brother 4"),
        ),
        Command(
            "endure",
            "Roll to resist harm or stress the story deals your character",
            subcommands=(_endure("endure_harm"), _endure("endure_stress")),
            help=(
                "Harm hurts the body and lowers health. Stress hurts the mind and lowers "
                "spirit. Moves usually ask for these rolls themselves. Use /endure when the "
                "story hurts your character on its own. The bar then asks you to roll.",
            ),
            examples=("/endure harm 2", "/endure stress 1"),
        ),
        Command(
            "asset",
            "List your assets, or show, buy, and change them",
            _assets,
            subcommands=(
                Command(
                    "list",
                    "List every asset you could buy",
                    _asset_list,
                    (Arg("category", CATEGORIES, optional=True),),
                    examples=("/asset list companion",),
                ),
                Command(
                    "show",
                    "Show an asset's abilities",
                    _asset_show,
                    (Arg("asset", _catalog),),
                    examples=("/asset show hawk",),
                ),
                Command(
                    "buy",
                    "Spend 3 experience on a new asset",
                    _asset_buy,
                    (
                        Arg("asset", _catalog),
                        Arg("ability", ("1", "2", "3"), optional=True, number=True),
                        Arg("stat change", STAT_CHANGES, repeat=True),
                    ),
                    help=(
                        "Some assets start with no ability marked, so give the ability to "
                        "mark. A few abilities change your stats: write each change after "
                        "the ability, such as +shadow or -heart.",
                    ),
                    examples=("/asset buy owl", "/asset buy shadow_kin 1 -heart +shadow"),
                ),
                Command(
                    "upgrade",
                    "Spend 2 experience to mark another ability of an asset you own",
                    _asset_upgrade,
                    (
                        _OWNED,
                        Arg("ability", _unmarked, number=True),
                        Arg("stat change", STAT_CHANGES, repeat=True),
                    ),
                    examples=("/asset upgrade archer 2",),
                ),
                Command(
                    "meter",
                    "Add to or take from an asset's meter, such as a companion's health",
                    _asset_meter,
                    (
                        Arg("asset", _with_meters),
                        Arg("meter", _asset_meters),
                        Arg("n", number=True),
                    ),
                    examples=("/asset meter hawk health -1",),
                ),
                Command(
                    "set",
                    "Fill in an asset's field, such as a companion's name",
                    _asset_set,
                    (
                        Arg("asset", _with_fields),
                        Arg("field", _asset_fields),
                        Arg("value", _field_choices, free=True, rest=True),
                    ),
                    examples=("/asset set hawk name Kestrel",),
                ),
                Command(
                    "debility",
                    "Make an asset count as a debility, or stop counting",
                    _asset_debility,
                    (_OWNED, Arg("state", ("on", "off"))),
                    examples=("/asset debility hawk on",),
                ),
                Command(
                    "harm",
                    "Owe Companion Endure Harm when your companion is hurt",
                    _asset_harm,
                    (Arg("companion", _companions), Arg("n", number=True)),
                    examples=("/asset harm hawk 2",),
                ),
                Command(
                    "use",
                    "Use Lorekeeper's or Slayer's third ability",
                    _asset_use,
                    (Arg("asset", USABLE), Arg("for", _uses, optional=True)),
                    help=(
                        "Lorekeeper browses the archive, one time only. Slayer takes a "
                        "trophy, for a ritual or a sojourn.",
                    ),
                    examples=("/asset use slayer ritual",),
                ),
                Command(
                    "discard",
                    "Remove an asset you own",
                    _asset_discard,
                    (_OWNED,),
                    examples=("/asset discard hawk",),
                ),
            ),
            help=(
                "Assets are your character's special talents, companions, and paths, each "
                "with three abilities. Marked abilities apply in play, and the app offers "
                "them when they fit a move. You earn experience by fulfilling vows, and you "
                "spend it on new assets and abilities.",
                "With no option, /asset lists the assets you own.",
            ),
            examples=("/asset", "/asset show archer", "/asset buy owl"),
        ),
        Command(
            "effects",
            "List lasting effects, or end one",
            _effects,
            subcommands=(
                Command(
                    "end",
                    "End a lasting effect by its number",
                    _effects_end,
                    (Arg("number", _effect_numbers, number=True),),
                    examples=("/effects end 1",),
                ),
            ),
            help=(
                "Some abilities and moves leave an effect that lasts, such as a ritual's "
                "bonus. The app ends most of them for you. End one by hand when the story "
                "says it's over.",
            ),
            examples=("/effects", "/effects end 1"),
        ),
        Command(
            "quit",
            "Leave the app. Your campaign is already saved",
            _quit,
            help=(
                "The app saves the campaign after every change, so nothing is lost. Play it "
                "again with ironsworn-tui play and the character's name. Ctrl+Q quits too.",
            ),
            examples=("/quit",),
        ),
    )
)
