"""The `ironsworn-tui` command."""

import argparse
import sys
from collections.abc import Sequence

from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import DecideError, TurnState, build_request, jevtester_server
from ironsworn_tui.experiment import SUITES_DIR, generated_files, load_phrasings
from ironsworn_tui.moves import CANNOT_TELL, NO_MOVE, Context, Initiative
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.settings import load_settings

TOP_MOVES = 3


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


def write_suites(args: argparse.Namespace) -> int:
    """Write the recognizer question sets and suites from the phrasings file."""
    files = generated_files(datasworn(), load_phrasings())
    for relative, text in files.items():
        path = SUITES_DIR / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
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

    w = commands.add_parser("write-suites", help="Write the recognizer suites.")
    w.set_defaults(func=write_suites)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command."""
    args = make_parser().parse_args(argv)
    return args.func(args)
