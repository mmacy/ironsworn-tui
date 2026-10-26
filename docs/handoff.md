# Handoff

If you're starting work on ironsworn-tui with no earlier context, read this page, then [`plan.md`](plan.md).

If you're new to the code, read [`architecture.md`](architecture.md) for how it's organized and how to make a first change.

## What this project is

ironsworn-tui is a terminal app for solo Ironsworn. A decision model reads what the player types and suggests the triggered move and stat. The player confirms with a keypress, and the app rolls and shows the outcome. The project is also an experiment: the user is learning where decision models work well, so measuring accuracy is as much a goal as the app.

## Where things are

| What | Where |
|---|---|
| This repository | `~/repos/ironsworn-tui`, remote `mmacy/ironsworn-tui` |
| The plan | `docs/plan.md` |
| Rules engine and data to vendor | `~/repos/osr-plugins/plugins/ironsworn-referee/skills/referee/` at commit `7e2e4a8`: `scripts/iron.py`, `scripts/test_iron.py`, and `references/datasworn/` |
| Move disambiguation guide | `references/move_disambiguation.md` in the same folder |
| Rules about player choices | `references/constitution.md` in the same folder |
| Decision model test tool | `~/repos/jevtester`. Run it with `uv run --project ~/repos/jevtester jevtester --config <path to this repo's jevtester.toml> ...`. Without `--config`, jevtester looks for `jevtester.toml` in the working directory and exits 2. |
| jevtester suite, question set, and policy examples | `~/repos/jevtester/suites/parley.yaml`, `suites/question-sets/parley.yaml`, and `suites/policies/parley.yaml` |

## Status

The app is playable. It covers every core move, all 78 assets and their abilities, the 23 asset moves, lasting effects, companions, fights, journeys, vows, and oracles. The app saves each answered message as a jevtester case in `suites/play-<context>.yaml`. [`architecture.md`](architecture.md) describes each module.

On the 120 hand-written recognizer cases, `decision-1@foundry` picks the right move 95 percent of the time on `exploring`, and `clef-flash@workers-ai` 87.5 percent. Play uses the guide criteria, stat questions without a `cannot_tell` option, and the `move` question's `cannot_tell` option. For a question typed after `/oracle` with no table, `decision-1@foundry` told yes or no questions from table questions for all 56 hand-written questions, picked a fitting table for 30 of 33, and an acceptable likelihood for 19 of 21. [`experiments/results.md`](https://github.com/mmacy/ironsworn-tui/blob/main/experiments/results.md) has the numbers and what's unmeasured.

What's open:

- The decision model sees only the core moves. Adding asset moves and ability conditions to its questions needs a separate experiment, and that starts only after the user agrees. It's the last part of build step 8 in the plan.
- Clef-flash's confidence is less calibrated than Decision-1's, so the policy needs per-target thresholds before play relies on Clef-flash.
- [`decision-model-guidance.md`](decision-model-guidance.md) lists what's still to test about the requests.

Rules for working on the project:

- Read [`decision-model-guidance.md`](decision-model-guidance.md) before changing a question, the criteria, or the state.
- Campaign files have a `schema_version`, and a file with any other version doesn't load. Raise `SCHEMA_VERSION` in `campaign.py` when the format changes, with no migration.
- The user documentation follows the Diataxis framework: the tutorial `getting-started.md`, the task guides `how-to.md`, the reference `reference.md`, and the explanation `playing.md`, all in `docs/`. Update them with any change to a command, key, or rule the app applies.
- `tests/test_style.py` fails on any `noqa`, `type: ignore`, or `pyright: ignore` in the package or tests.
- Never use the phrase "What do you do?" in UI text or prose. The user asked for that explicitly.
- The user said to use `decision-1@foundry` for live calls. The Ollama models aren't downloaded, and won't be while the user is on a hotspot. The user approved `clef-flash@workers-ai` as the second target for the recognizer suites.
- The user allowed changing `~/repos/jevtester` if it makes sense, for example to send structured criteria.
- `diary/` contains the dev diary. Add an entry when you merge a piece of work or make a decision.
- To check a rule, search the rulebook from `~/repos/shelf-of-holding` with `uv run shelf search "<terms>"`, then `uv run shelf show "DriveThruRPG/Shawn Tomkin/Ironsworn/Ironsworn-Rulebook.pdf" <page>`.

## How to work

- Write a change's tests before its implementation, and run the command that shows it works before you call it done.
- Don't call a hosted model in the default test run. Record jevtester's JSON output into `tests/fixtures/` and test against that. Put live calls behind `-m live`.
- Keep rules decisions in code and mechanical choices with the player. The model only suggests a move and a stat.
- Refactor freely and update every call site. Don't keep aliases or deprecated code.

## Gates

Run these from the repository root before every commit:

```sh
uv run ruff format --check
uv run ruff check
uv run pyright
uv run pytest
uv run zensical build --clean
```

Fix a finding in the code. Don't add `noqa`, `type: ignore`, or ignore lists.

## Documentation site

The docs in `docs/` are published as a site built with [Zensical](https://zensical.org/). `zensical.toml` contains the site's settings and navigation. Add a new page to `nav` there, or it won't appear in the site's navigation. The dev diary in `diary/` isn't part of the site.

- Build the site with `uv run zensical build --clean`. It writes to `site/`, which git ignores. The build must finish with "No issues found", so fix any broken link or anchor it reports.
- Preview the site with `uv run zensical serve`.
- `.github/workflows/docs.yml` builds the site and deploys it to GitHub Pages on every push to `main`. It needs the repository's Pages source set to GitHub Actions.

## Screenshots

`scripts/screenshots.py` draws the SVG screenshots in `docs/images/`. It runs the real app headlessly at 120 by 36 with Textual's pilot, and uses the loaded dice and `FixtureDecider` from `tests/support.py`, so it calls no model and needs no network. Each run draws the same screens.

Run it from the repository root after any change to what the screen shows:

```sh
uv run python -m scripts.screenshots
```

To add a screenshot, add a drive function to `SCREENS` in the script, run it, and embed the new file with alt text that describes what it shows.

## Decision model targets

`~/repos/jevtester/jevtester.toml` lists the targets. This repository's `jevtester.toml` copies the ones this app uses. Check them with `uv run --project ~/repos/jevtester jevtester --config jevtester.toml targets check`.

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
