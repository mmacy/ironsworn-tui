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
- Build step 4 is done. The user approved the 120 cases on 2026-10-24. Both targets clear the 80 percent bar on `exploring`: `decision-1@foundry` at 95 percent and `clef-flash@workers-ai` at 87.5 percent. Play uses the guide criteria, stat questions without a `cannot_tell` option, and the `move` question's `cannot_tell` option. [`experiments/results.md`](../experiments/results.md) has the numbers and what's unmeasured.
- Clef-flash's confidence is less calibrated than Decision-1's, so the policy needs per-target thresholds before play relies on it.
- Build step 5 is done: `campaign.py` (the saved campaign), `outcomes.py` (each move's effects per result), `policy.py` (thresholds to a suggestion), and `turn.py` (the game loop, with no UI). The module docstring of `turn.py` gives the order the TUI calls it in.
- Known gaps in step 5, each a Note or an `/adjust` for now:
  - Face Death and Face Desolation have outcome entries, but no table result triggers them.
  - Companion Endure Harm waits for assets (step 8).
  - Sojourn's extra choice for a bond isn't applied.
  - Bare yourself's +1 foe harm isn't applied.
  - A rolled card that isn't resolved is lost on restart.
- Draw the Circle offers up to two boasts, as the vendored Datasworn says. The rulebook says up to three.
- Build step 6 is done: `app.py` (the Textual app), `commands.py` (the `/` commands, with no UI), and the `ironsworn-tui new` and `ironsworn-tui play` commands. The README shows how to play.
- `tests/test_style.py` fails on any `noqa`, `type: ignore`, or `pyright: ignore` in the package or tests.
- Never use the phrase "What do you do?" in UI text or prose; the user asked for that explicitly.
- Build step 7 is done: each answered message becomes a case in `suites/play-<context>.yaml`, saved through the running jevtester server. `n` on the suggestion bar saves a `no_move` case, and Escape saves nothing.
- Build step 8, assets, is in progress. The user asked for every asset, not a subset (2026-10-25). The plan splits it into four pull requests. Part 1, the catalog and ownership, is done: typed asset models in `rules/datasworn.py`, owned assets in `campaign.py`, buying and upgrading in `assets.py`, and the `/asset` commands. Part 2 is done: `abilities.py` holds the hand-written ability table and the helpers that apply a boost to a result, and the turn engine and TUI apply them. Part 3, asset moves, lasting effects, and companions, is next; the table's reminders that mention part 3 list what it covers. Face Death and Face Desolation still aren't triggered from a result, so boosts for them can't be used yet.
- Campaign files are now schema version 2, and version 1 files don't load. No campaigns existed when this changed.
- The user said to use `decision-1@foundry` for live calls. The Ollama models aren't downloaded, and won't be while the user is on a hotspot. The user approved `clef-flash@workers-ai` as the second target for the recognizer suites.
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
