"""The `ironsworn-tui` command."""

import argparse
import random
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import get_args

from ironsworn_tui.app import IronswornApp
from ironsworn_tui.campaign import Campaign, create_character, new_campaign
from ironsworn_tui.cases import play_suite_name
from ironsworn_tui.commands import parse_rank
from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import DecideError, TurnState, build_request, jevtester_server
from ironsworn_tui.experiment import (
    SUITES_DIR,
    dump_yaml,
    generated_files,
    load_phrasings,
    play_suite,
)
from ironsworn_tui.moves import CANNOT_TELL, NO_MOVE, Context, Initiative
from ironsworn_tui.policy import load_thresholds
from ironsworn_tui.rules.datasworn import Stat, datasworn
from ironsworn_tui.rules.errors import UnknownIdError
from ironsworn_tui.settings import load_settings
from ironsworn_tui.turn import TurnEngine

TOP_MOVES = 3
STATS: dict[str, Stat] = {stat: stat for stat in get_args(Stat.__value__)}


def _option_name(option: str) -> str:
    if option in (NO_MOVE, CANNOT_TELL):
        return option.replace("_", " ").capitalize()
    if option == "attack":
        return "Attack"
    return datasworn().move(option).name


def suggest(args: argparse.Namespace) -> int:
    """Print the moves and stat the decision model suggests for one message."""
    context = Context(args.context)
    initiative: Initiative | None = args.initiative if context is Context.FIGHT else None
    if context is Context.FIGHT and initiative is None:
        initiative = "character"
    state = TurnState(
        name=args.name,
        character=args.character,
        situation=args.situation,
        context=context,
        initiative=initiative,
        player_says=args.text,
    )
    settings = load_settings()
    target = args.target or settings.target
    request = build_request(datasworn(), state, CriteriaStyle(args.style))
    try:
        with jevtester_server(settings) as client:
            decision = client.decide(request, target)
    except DecideError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 3
    if decision.move is None:
        print(f"No suggestion: {decision.error}")
        return 3
    ranked = decision.move.ranked()
    top_p = ranked[0][1]
    second_p = ranked[1][1] if len(ranked) > 1 else 0.0
    ratio = f"{top_p / second_p:.1f}" if second_p > 0 else "inf"
    print(f"Target: {target}, {decision.latency_ms:.0f} ms")
    print(f"Confidence: {decision.move.confidence:.2f}, top to second: {ratio}")
    for number, (option, probability) in enumerate(ranked[:TOP_MOVES], start=1):
        print(f"{number}. {_option_name(option)}: {probability:.3f}")
    stat = decision.stat_for(decision.move.choice)
    if stat is not None:
        print(f"Stat: {stat.choice} ({stat.ranked()[0][1]:.3f})")
    return 0


def _campaign_path(name: str) -> Path:
    return load_settings().campaigns_dir / f"{name}.json"


def new(args: argparse.Namespace) -> int:
    """Create a character and a campaign with their background vow."""
    path = _campaign_path(args.name)
    if path.exists():
        print(f"Error: {path} already exists", file=sys.stderr)
        return 2
    try:
        stats: dict[Stat, int] = {}
        for pair in args.stats.split(","):
            stat, _, value = pair.partition("=")
            if stat not in STATS:
                raise ValueError(f"unknown stat {stat!r}")
            stats[STATS[stat]] = int(value)
        character = create_character(
            datasworn(),
            args.name,
            args.description,
            stats,
            args.assets.split(","),
            harm=args.harm,
        )
        campaign = new_campaign(character, args.vow, parse_rank(args.rank))
    except (ValueError, UnknownIdError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    campaign.save(path)
    print(path)
    return 0


def play(args: argparse.Namespace) -> int:
    """Play a campaign in the TUI."""
    settings = load_settings()
    path = _campaign_path(args.name)
    if not path.exists():
        print(
            f"Error: no campaign at {path}. Create one with `ironsworn-tui new`.", file=sys.stderr
        )
        return 2
    try:
        campaign = Campaign.load(path)
    except (OSError, ValueError) as error:
        print(f"Error: can't load {path}: {error}", file=sys.stderr)
        return 2
    with ExitStack() as stack:
        decider = None
        if not args.no_model:
            print(f"Starting jevtester for {settings.target}…", file=sys.stderr)
            try:
                decider = stack.enter_context(jevtester_server(settings))
            except (DecideError, OSError) as error:
                campaign.add_log("note", f"Playing without move suggestions: {error}")
        try:
            engine = TurnEngine(
                campaign,
                datasworn(),
                random.Random(),
                load_thresholds(settings.target),
                decider=decider,
                target=settings.target,
                path=path,
                cases=decider,
            )
        except ValueError as error:
            print(f"Error: can't play {path}: {error}", file=sys.stderr)
            return 2
        IronswornApp(engine).run()
    return 0


def write_suites(args: argparse.Namespace) -> int:
    """Write the recognizer question sets and suites from the phrasings file."""
    files = generated_files(datasworn(), load_phrasings())
    for relative, text in files.items():
        path = SUITES_DIR / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(path.relative_to(SUITES_DIR.parent))
    # The play suites hold cases from play, so they're created once and never rewritten.
    for context in Context:
        path = SUITES_DIR / f"{play_suite_name(context)}.yaml"
        if not path.exists():
            path.write_text(dump_yaml(play_suite(context)))
            print(path.relative_to(SUITES_DIR.parent))
    return 0


def make_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(prog="ironsworn-tui", description="Solo Ironsworn.")
    commands = parser.add_subparsers(dest="command", required=True)

    s = commands.add_parser("suggest", help="Show the moves the decision model suggests.")
    s.add_argument("text", help="What the player types.")
    s.add_argument("--context", choices=[c.value for c in Context], default="exploring")
    s.add_argument("--initiative", choices=["character", "foe"], default=None)
    s.add_argument("--name", default="Kira")
    s.add_argument("--character", default="Kira, a hunter")
    s.add_argument("--situation", default="")
    s.add_argument("--style", choices=[c.value for c in CriteriaStyle], default="guide")
    s.add_argument("--target", default=None, help="Defaults to the settings file's target.")
    s.set_defaults(func=suggest)

    n = commands.add_parser("new", help="Create a character and a campaign.")
    n.add_argument("name", help="The character's name, which also names the campaign file.")
    n.add_argument("--description", required=True, help="A few words, such as 'a hunter'.")
    n.add_argument("--stats", required=True, help="edge=3,heart=2,iron=2,shadow=1,wits=1")
    n.add_argument(
        "--assets",
        required=True,
        help="Three asset ids. A companion adds its starting ability: archer,hawk:2,wright.",
    )
    n.add_argument("--vow", required=True, help="The background vow.")
    n.add_argument("--rank", default="epic", help="The background vow's rank.")
    n.add_argument("--harm", type=int, choices=[1, 2], default=2, help="2 with a deadly weapon.")
    n.set_defaults(func=new)

    p = commands.add_parser("play", help="Play a campaign.")
    p.add_argument("name", help="The campaign's name.")
    p.add_argument("--no-model", action="store_true", help="Play without move suggestions.")
    p.set_defaults(func=play)

    w = commands.add_parser(
        "write-suites", help="Write the recognizer suites, and create missing play suites."
    )
    w.set_defaults(func=write_suites)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command."""
    args = make_parser().parse_args(argv)
    return args.func(args)
