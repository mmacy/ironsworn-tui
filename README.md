# ironsworn-tui

ironsworn-tui is a terminal app for playing *Ironsworn*, a solo tabletop roleplaying game. You type what your character does, and a decision model suggests which move that action triggers. You confirm the move with a key, and the app rolls the dice, shows the result, and updates your character.

## What you need

- Python 3.14.
- [uv](https://docs.astral.sh/uv/).
- A checkout of jevtester at `~/repos/jevtester`. The app runs it to ask the decision model.
- A sign-in for the decision model. The default target, `decision-1@foundry`, uses the Azure CLI, so run `az login`. The `clef-flash@workers-ai` target uses Wrangler, so run `npx wrangler login`.

If you don't have jevtester or a sign-in, you can still play. Start the game with `--no-model`, and you'll pick each move from a list yourself.

## Install

```sh
git clone git@github.com:mmacy/ironsworn-tui.git
cd ironsworn-tui
```

There's no separate install step. The first time you run `uv run`, uv installs the app's dependencies.

## Quickstart

From the `ironsworn-tui` folder, sign in, create a character, and start playing:

```sh
az login
uv run ironsworn-tui new Kira --description "a hunter" --stats edge=2,heart=2,iron=1,shadow=1,wits=3 --assets archer,hawk:2,wright --vow "Avenge my village"
uv run ironsworn-tui play Kira
```

Type what Kira does and press Enter. When the app suggests a move, press Enter to roll it, then Enter again to apply the result. Press Ctrl+Q to quit. The app saves your campaign after every turn, so `play Kira` picks up where you stopped.

When the model answers a message and you make a move or press `n`, the app saves that message as a test case in `suites/play-<context>.yaml`. Those files change as you play.

## Documentation

- Tutorial: [Getting started](docs/getting-started.md) walks you through a first character and a first session.
- How-to guides: [How-to guides](docs/how-to.md) cover tasks like choosing a model target, playing without the model, fights, journeys, buying assets, and fixing mistakes.
- Reference: [Reference](docs/reference.md) lists every command, flag, key, `/` command, and setting.
- Explanation: [Playing Ironsworn](docs/playing.md) explains the rules as the app handles them.

The full rules are in the *Ironsworn* rulebook, a free download from the publisher, Tomkin Press, at [tomkinpress.com](https://tomkinpress.com/products/ironsworn-digital-edition).

## Development

Run these four gates from the repository root before every commit:

```sh
uv run ruff format --check
uv run ruff check
uv run pyright
uv run pytest
```

The developer documentation is in three files:

- [`docs/handoff.md`](docs/handoff.md) is where to start work on the project.
- [`docs/plan.md`](docs/plan.md) is the build plan.
- [`docs/decision-model-guidance.md`](docs/decision-model-guidance.md) covers the decision model's questions, criteria, and state.

## License

This repository is licensed under [CC BY-NC-SA 4.0](LICENSE). The rules in `ironsworn_tui/rules/` are ported from the Ironsworn referee plugin's `iron.py`, which has the same license. *Ironsworn* is by Shawn Tomkin. The Datasworn data in `ironsworn_tui/data/datasworn/` is CC BY 4.0 or CC BY-NC-SA 4.0, file by file, as its [`LICENSE.md`](ironsworn_tui/data/datasworn/LICENSE.md) lists.
