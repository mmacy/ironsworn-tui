# ironsworn-tui

A terminal app for solo Ironsworn. A decision model suggests which move your action triggers, you confirm it, and the app rolls and shows the outcome.

The app is under construction. See [`docs/plan.md`](docs/plan.md) for the plan and [`docs/handoff.md`](docs/handoff.md) to start work.

## Play

```sh
uv sync
uv run ironsworn-tui new Kira --description "a hunter" --stats edge=2,heart=2,iron=1,shadow=1,wits=3 --assets archer,hawk,wright --vow "Avenge my village"
uv run ironsworn-tui play Kira
```

Type what your character does and press Enter. The app asks the decision model in `ironsworn-tui.toml` which move it triggers, through jevtester. Press Enter on the suggestion bar to roll, then pick any choices on the roll card. Text that starts with `/` is a command: `/oracle`, `/ask`, `/vow`, `/scene`, `/target`, `/tide`, `/adjust`, and `/moves`. Add `--no-model` to `play` to pick every move from the list yourself.

## Development

```sh
uv sync
uv run ruff format --check
uv run ruff check
uv run pyright
uv run pytest
```

## License

This repository is licensed under [CC BY-NC-SA 4.0](LICENSE). The rules in `ironsworn_tui/rules/` are ported from the Ironsworn referee plugin's `iron.py`, which has the same license. *Ironsworn* is by Shawn Tomkin. The Datasworn data in `ironsworn_tui/data/datasworn/` is CC BY 4.0 or CC BY-NC-SA 4.0, file by file, as its [`LICENSE.md`](ironsworn_tui/data/datasworn/LICENSE.md) lists.
