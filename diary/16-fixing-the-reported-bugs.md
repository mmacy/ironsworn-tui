# 16: Fixing the reported bugs

Sunday 25 October 2026, 09:10 to 09:57 PDT. Written by Claude Opus 5.5, a subagent of the lead agent, from the merged PRs and their reports.

## The user's instructions

The user said: "Fix bugs when you or subagents find them, please." They also said: "This is greenfield. No back compat effort should be expended. No shims, docs about what was. Build for now, there are no users yet, including me." Then they corrected it: "*no docs about what was".

Subagents fixed the bugs and known gaps listed in each repo's handoff in five PRs, two in ironsworn-tui and three in jevtester. A sixth PR swept this repo's docs of text about the past.

## ironsworn-tui PR #24: five command bugs

Each fix has a test written first.

- **Quoted errors.** `/vow mark Nope` showed `"no vow named 'Nope'"`, with quotes, because the error was a `KeyError`. `Campaign.vow` and `Character.asset` raise `NotFoundError`, a `KeyError` whose `str` is its message, so the log shows `no vow named 'Nope'`.
- **The `/asset buy` usage line.** Stat changes apply only to Shadow-Kin 1 and Battle-Scarred 1, which start unmarked, so they always follow an ability number. The usage line reads `buy <asset> [ability [+stat -stat]]`.
- **`/adjust momentum` past -6.** It logs the same Face a Setback note as moves do. The note moved from `turn._setback_note` to `campaign.setback_note`.
- **Companion given names.** `find_asset` also matches an owned companion's `name` field, so `/asset meter Kestrel health -1` works. Catalog ids and names win a tie.
- **Move keys.** The suggestion bar's moves past the ninth take `A` to `Z`, because the lowercase letters `e h i s w a n` already set the stat or act. The hint names the keys in use, such as `1-9 A-J or arrows move`.

The result was 942 tests.

## ironsworn-tui PR #25: six rules gaps

Each fix was checked against the Ironsworn rulebook. The page numbers are the printed pages.

- **Sojourn and bonds, page 71.** Sojourn asks whether you share a bond with the community. A bond adds +1 to the roll and one more recovery choice on a hit. The player answers; the app doesn't infer it.
- **Bare yourself, page 73.** It adds 1 to the foes' harm until the fight ends (`Campaign.foe_harm_bonus`).
- **Hold no iron, page 73.** It sets the character's harm to 1 until the fight ends, then restores it (`Campaign.harm_after_fight`).
- **Boasts, page 73.** A strong hit on Draw the Circle allows up to three boasts, as the rulebook says. The vendored Datasworn says two.
- **End the Fight, page 82.** The rulebook allows any decisive move as the setup. The app offers End the Fight after a strong hit on any move made in a fight, except Enter the Fray, Draw the Circle, Battle, progress moves, and the rolled suffer moves. The foe still needs one full box, and Escape declines the offer.
- **The saved roll card.** An unresolved card is saved as `Campaign.pending_card` and rebuilt on load with the same dice. `SCHEMA_VERSION` went to 3, with no migration.

The result was 963 tests.

## jevtester PR #27: limits and the missing UI build

- **Image limits and `tokens_per_minute`.** Preflight reads each image and rejects a request over `max_image_bytes`, `max_total_image_bytes`, or `image_formats` before sending it. It recognizes PNG, JPEG, and WebP from the file's first bytes. Runs pace requests by `tokens_per_minute` as they already did by `requests_per_minute`, using preflight's estimate of JSON bytes divided by 4.
- **The missing UI build.** When the UI isn't built, `jevtester serve` shows a page with the build instructions (`cd web`, `npm install`, `npm run build`) instead of a 404. The API keeps working, and a build made while the server runs is served on reload.

## jevtester PR #28: config errors, the Foundry check, and the local config

- **Config errors.** `load_config` raises `ConfigError` for a file that can't be read, isn't UTF-8, or isn't valid TOML, and the CLI exits 2 with the message.
- **A `systemone` target without `base_url`.** It's a config validation error, not a traceback.
- **The Foundry health check.** It reports `No Foundry resource` while `base_url` names the placeholder `example-resource`, without asking `az` for a token. Otherwise it gets a token, then sends a GET to `base_url` without the token. That reaches no model, so it isn't billed.
- **The local config.** When jevtester finds its config itself, `jevtester.local.toml` is deep-merged over `jevtester.toml`: tables merge, local values win, and arrays are replaced. `--config` still reads one file, and ironsworn-tui always passes it, so the merge doesn't affect this app.

## jevtester PR #29: runs and suites

- **Run ownership.** Each run records the store that started it. A store holds an OS lock while it's open, and the kernel releases it when the process ends. Only runs whose owner's lock is free are marked failed, so one jevtester process no longer fails another's running runs.
- **Suite paths.** `run`, `probe`, `suite check`, and `case add` load a value with a directory or a `.yaml` suffix from that file, with its question set and policy from the file's directory.
- **The `cancelled` error code.** Nothing returned it, so it's removed from the contract and the UI.
- **`case add` comments.** It appends the case after the last one, so the rest of the file, comments included, stays byte for byte.

The result was 328 pytest tests. PRs #27 to #29 fixed all 10 known issues in jevtester's handoff.

## The sweep for docs about what was

This repo's PR sweeps the README, `docs/`, and the docstrings and comments in `ironsworn_tui/`, `scripts/`, and `tests/`. The code needed only two docstrings changed, in `criteria.py` and `decide.py`, which named "the step 4 experiment" instead of the recognizer experiment. The README needed nothing.

- **`docs/handoff.md`.** The status list of 16 items, mostly "Build step N is done" and "the gaps are fixed", became a short statement of what the app covers, the recognizer accuracy, what's open, and the working rules. The how-to-work rule about stopping after build step 4 is gone. The gates list gains `zensical build --clean`.
- **`docs/plan.md`.** The plan said End the Fight follows only Strike or Clash, which PR #25 changed, and that the suggestion bar's moves use 1 to 9, which PR #24 changed. It said the repo was private, named `assets.py` for the ability table that lives in `abilities.py`, listed a `per_target` policy section that doesn't exist, and listed only 8 modules. Each of these is corrected. Sentences such as "Build step 4 dropped a `cannot_tell` option" and "The plan uses whichever scores better" now state the result. The build order stays, with one line saying steps 1 through 8.3 are built and 8.4 is open.
- **`docs/decision-model-guidance.md`.** "Build step 3 applied" and "Build step 4 measured" became what the requests do and what the recognizer experiment measured.
- **`docs/playing.md`.** The "Known gaps" section, which said there are none, became "When the app can't apply a result".

The sweep found no bugs in the code. All five gates pass with 963 tests.
