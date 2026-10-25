# ironsworn-tui

ironsworn-tui is a terminal app for playing *Ironsworn*, a solo tabletop roleplaying game. You type what your character does, and a decision model suggests which move that action triggers. You confirm the move with a key, and the app rolls the dice, shows the result, and updates your character.

![The play screen. The character panel on the left shows the stats, meters, assets, and vows of Blarg the Destructor. The log on the right shows their latest action, and the suggestion bar below it suggests Face Danger with edge.](images/suggestion.svg)

## What you need

- Python 3.14.
- [uv](https://docs.astral.sh/uv/).
- A checkout of [jevtester](https://github.com/mmacy/jevtester) at `~/repos/jevtester`. The app runs it to ask the decision model.
- Your own decision model deployment, with its details in `jevtester.local.toml`. [How to set up the model target](how-to.md#how-to-set-up-the-model-target) shows how.
- A sign-in for the decision model. The default target, `decision-1@foundry`, uses the Azure CLI, so run `az login`. The `clef-flash@workers-ai` target uses Wrangler, so run `npx wrangler login`.

If you don't have jevtester or a sign-in, you can still play. Start the game with `--no-model`, and you'll pick each move from a list yourself.

## Quickstart

Clone the repository, sign in, create a character, and start playing:

```sh
git clone https://github.com/mmacy/ironsworn-tui.git
cd ironsworn-tui
az login
uv run ironsworn-tui new Blarg --description "the Destructor" --stats edge=2,heart=2,iron=1,shadow=1,wits=3 --assets archer,hawk:2,wright --vow "Avenge my village"
uv run ironsworn-tui play Blarg
```

There's no separate install step. The first time you run `uv run`, uv installs the app's dependencies.

Type what Blarg does and press Enter. When the app suggests a move, press Enter to roll it, then Enter again to apply the result. Press Ctrl+Q to quit. The app saves your campaign after every turn, so `play Blarg` picks up where you stopped.

## Documentation

- Tutorial: [Getting started](getting-started.md) walks you through a first character and a first session.
- How-to guides: [How-to guides](how-to.md) cover tasks like choosing a model target, playing without the model, fights, journeys, buying assets, and fixing mistakes.
- Reference: [Reference](reference.md) lists every command, flag, key, `/` command, and setting.
- Explanation: [Playing Ironsworn](playing.md) explains the rules as the app handles them.
- Development: [Handoff](handoff.md) is where to start work on the project.

The full rules are in the *Ironsworn* rulebook, a free download from the publisher, Tomkin Press, at [tomkinpress.com](https://tomkinpress.com/products/ironsworn-digital-edition).

## Thanks

*Ironsworn* is written and published by Shawn Tomkin. Learn about the game on its [home page at Tomkin Press](https://tomkinpress.com/pages/ironsworn), and get the free digital edition or a print copy from [Tomkin Press](https://tomkinpress.com/products/ironsworn-digital-edition) or [DriveThruRPG](https://www.drivethrurpg.com/en/product/238369/Ironsworn). Thanks to Shawn Tomkin for the game and for releasing it under an open license.

The moves, assets, and oracles come from [Datasworn](https://github.com/rsek/datasworn), the Ironsworn rules in machine-readable form.

## License

The repository is licensed under [CC BY-NC-SA 4.0](https://github.com/mmacy/ironsworn-tui/blob/main/LICENSE). *Ironsworn* is by Shawn Tomkin. Ironsworn is a trademark of Shawn Tomkin. This is not an official Ironsworn product.
