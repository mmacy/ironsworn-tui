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

- The repository has the plan, this handoff, a README, and a `.gitignore`. No code exists yet.
- Start with build step 1, the scaffold.

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

- `decision-1@foundry` (Microsoft-Decision-1) answered in about 1 second when tested on 2026-10-24.
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
