# Handoff

If you're starting work on ironsworn-tui with no earlier context, read this page, then [`plan.md`](plan.md). Then start at the first unfinished step in the plan's build order.

## What this project is

ironsworn-tui is a terminal app for solo Ironsworn. A decision model reads what the player types and suggests the triggered move and stat. The player confirms with a keypress, and the app rolls and shows the outcome. The project is also an experiment: the user is learning where decision models work well, so measuring accuracy matters as much as the app.

## Where things are

| What | Where |
|---|---|
| This repository | `~/repos/ironsworn-tui`, remote `mmacy/ironsworn-tui` (private) |
| The plan | `docs/plan.md` |
| Rules engine and data to vendor | `~/repos/osr-plugins/plugins/ironsworn-referee/skills/referee/` at commit `7e2e4a8`: `scripts/iron.py`, `scripts/test_iron.py`, and `references/datasworn/` |
| Move disambiguation guide | `references/move_disambiguation.md` in the same folder |
| Rules about player choices | `references/constitution.md` in the same folder |
| Decision model test tool | `~/repos/jevtester`. Run it with `uv run --project ~/repos/jevtester jevtester --config <path to this repo's jevtester.toml> ...`. Without `--config`, jevtester looks for `jevtester.toml` in the working directory and exits 2. |
| jevtester suite, question set, and policy examples | `~/repos/jevtester/suites/parley.yaml`, `suites/question-sets/parley.yaml`, and `suites/policies/parley.yaml` |

## Status

- Build step 1 is done: the uv project, the vendored Datasworn data in `ironsworn_tui/data/datasworn/`, and the typed rules port in `ironsworn_tui/rules/`.
- The port fixes two `iron.py` bugs. Burning momentum now cancels only the challenge dice below the momentum, so it can't make a result worse. Sub-rolls now follow the `oracle_rollable:` ids that `iron.py` couldn't resolve. Momentum also stops at -6 now, and any loss past that is reported as `setback` for Face a Setback.
- Build step 2 is done: typed pydantic move models in `ironsworn_tui/rules/datasworn.py`, and the move groups, contexts, and stat questions in `ironsworn_tui/moves.py`.
- Build step 3 is done: `ironsworn_tui/decide.py` builds the request, starts one `jevtester serve`, and parses the answers. `ironsworn_tui/criteria.py` has the two criteria styles. Read [`decision-model-guidance.md`](decision-model-guidance.md) before changing a question, the criteria, or the state.
- Start with build step 4, the recognizer experiment.
- The user said to use `decision-1@foundry` for live calls. The Ollama models aren't downloaded, and won't be while the user is on a hotspot. Ask before adding a second hosted target, such as `clef-flash@workers-ai`, to an experiment.
- The user allowed changing `~/repos/jevtester` if it makes sense, for example to send structured criteria.
- `diary/` holds the dev diary. Add an entry when a step or decision lands.
- To check a rule, search the rulebook from `~/repos/shelf-of-holding` with `uv run shelf search "<terms>"`, then `uv run shelf show "DriveThruRPG/Shawn Tomkin/Ironsworn/Ironsworn-Rulebook.pdf" <page>`.

## How to work

- Write a step's tests before its implementation. Each build step ends with a command that shows it works, so run it before you call the step done.
- Don't call a hosted model in the default test run. Record jevtester's JSON output into `tests/fixtures/` and test against that. Put live calls behind `-m live`.
- Keep rules decisions in code and mechanical choices with the player. The model only suggests a move and a stat.
- After build step 4, stop and give the user the accuracy numbers from `jevtester report` before you start step 5.
- Refactor freely and update every call site. Don't keep aliases or deprecated code.

## Gates

Run these from the repository root before every commit:

```sh
uv run ruff format --check
uv run ruff check
uv run pyright
uv run pytest
```

Fix a finding in the code. Don't add `noqa`, `type: ignore`, or ignore lists.

## Decision model targets

`~/repos/jevtester/jevtester.toml` lists the targets. Build step 3 copies the ones this app uses into this repository's `jevtester.toml`. Check them with `uv run --project ~/repos/jevtester jevtester --config jevtester.toml targets check`.

- `decision-1@foundry` (Microsoft-Decision-1) answered in about 1 second when tested on 2026-10-24, and in about 0.4 seconds on a warm `jevtester serve`.
- `clef-flash@workers-ai` answered in 2 to 3 seconds and was less confident on the same inputs.
- `clef-flash@ollama` isn't available yet, because its download isn't finished.

## Credentials

- This app stores no credentials. jevtester signs in for each target: Foundry through the `az` sign-in, and Workers AI through the Wrangler sign-in.
- Never print, log, or commit a token or key.
- Don't start or resume a model download without asking the user. The machine is sometimes on a phone hotspot.

## Repository rules

- Change `main` only through pull requests. Cut each branch from `origin/main`, and work in a worktree beside the main checkout: `git worktree add ../ironsworn-tui-<branch> -b <branch> origin/main`.
- Before you open a pull request, run `git log --oneline origin/main..HEAD` and confirm it lists only the branch's commits.
- You may merge your own pull request once the gates pass.

## Writing style

- Use sentence case for headings and for every UI label, key hint, and panel title.
- UI strings are labels or facts the player acts on. Don't add sentences that explain the UI.
- Don't hard-wrap Markdown. Don't use em dashes.
- Docstrings follow the Google style, in Markdown for mkdocstrings. Use built-in generics like `list[str]`, and don't use `from __future__ import annotations`.
