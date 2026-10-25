# ironsworn-tui

A terminal app for solo Ironsworn. A decision model suggests which move your action triggers, you confirm it, and the app rolls and shows the outcome.

The app is under construction. See [`docs/plan.md`](docs/plan.md) for the plan and [`docs/handoff.md`](docs/handoff.md) to start work.

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
