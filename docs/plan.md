# ironsworn-tui plan

ironsworn-tui is a terminal app for playing solo Ironsworn. The player types what their character does. A decision model suggests which move that action triggers and which stat it uses. The player confirms the suggestion with a keypress, and the app rolls the dice, shows the move's outcome text, and applies the outcome to the character.

The app has no LLM narrator. In solo Ironsworn the player writes the fiction, so the app only needs to recognize moves, roll dice, apply outcomes, look up tables, and track the character.

## Goals

- Learn where decision models work well and where they don't, using real play as the test data.
- Recognize the triggered move from free text, and ask the player when the model isn't sure.
- Keep every roll deterministic and every rules decision in code or with the player, never with the model.
- Save every message and the move and stat the player confirmed as a jevtester case, so accuracy can be measured and compared across models.

## Non-goals

- Narration, NPC dialogue, or oracle interpretation by a model.
- Co-op play, Ironsworn: Delve, and Ironsworn: Starforged.
- A web UI.
- Reading or writing the Ironsworn plugin's campaign files (`CHARACTER.md`, `VOWS.md`, and the rest). Claude writes those files as prose, so the app would have to parse free text to read them. Campaigns are JSON, as [Campaign state](#campaign-state) describes.
- Applying asset abilities in the first version. The player adds an asset's bonus by hand with an add key. Build step 8 covers assets.

## Sources

| Source | What we take | Where |
|---|---|---|
| osr-plugins, Ironsworn referee plugin | The Datasworn YAML, and `iron.py` and its tests as the reference for the port | `~/repos/osr-plugins/plugins/ironsworn-referee/skills/referee/`, commit `7e2e4a8` |
| Move disambiguation guide | The move criteria and the known ambiguities | `references/move_disambiguation.md` in the same folder |
| Play constitution | Which choices belong to the player, and how initiative works | `references/constitution.md` in the same folder |
| jevtester | The `decide`, `run`, `report`, and `case add` commands, the suite, question set, and policy formats, and the targets | `~/repos/jevtester` |

`iron.py` is a CLI, not a library. Only `action_roll()` and `build_indices()` return values. Progress rolls, suffer moves, oracles, and momentum bounds exist only as `cmd_*` functions that print JSON, and its error helper calls `sys.exit(2)`. It also fails this project's gates: ruff and pyright both report findings, and `test_iron.py` uses `# noqa` and runs `iron.py` as a subprocess. So build step 1 ports the rules into typed functions in `ironsworn_tui/rules/` and ports the tests to call them, using `iron.py` as the reference for the math.

The Datasworn move data contains the stat choices. Each move's `trigger.conditions` lists its approaches, and each condition has a `method` (`player_choice`, `lowest`, or `highest`) and the stats it rolls with. For example, Face Danger lists five `player_choice` approaches ("With speed, agility, or precision" uses edge). Single-stat moves have a condition with no text. Each move also has a `roll_type`: `action_roll`, `progress_roll`, `special_track`, or `no_roll`.

## Licensing

The Datasworn files are CC BY 4.0 or CC BY-NC-SA 4.0, file by file. `iron.py` and the plugin's guides are CC BY-NC-SA 4.0, and the port is a derived work. Vendor the Datasworn data with its `LICENSE.md`, and license this repository under CC BY-NC-SA 4.0 to match. The repository is private for now.

## Architecture

```text
ironsworn_tui/
  rules/       # typed port of iron.py: action and progress rolls, momentum, suffer moves, oracles, Datasworn models
  outcomes.py  # the effect of each chat move's outcome on the campaign
  moves.py     # which moves the chat can trigger in the current context
  decide.py    # builds the request, calls jevtester, parses the answers
  campaign.py  # pydantic models for the character, vows, foes, and journeys; JSON persistence
  turn.py      # one chat message from text to applied outcome, with no UI code
  cases.py     # saves each turn as a jevtester case
  app.py       # the Textual app
```

`turn.py` contains the game loop and doesn't import Textual, so tests can run the loop without a terminal. The TUI is a thin layer over it.

## Configuration

The repository root has two config files:

- `ironsworn-tui.toml` has the app's settings: `jevtester_project` (the path of the jevtester checkout, default `~/repos/jevtester`), `target` (default `decision-1@foundry`), and `campaigns_dir` (default `campaigns`).
- `jevtester.toml` is a jevtester config for this repository. It copies the target entries the app uses from `~/repos/jevtester/jevtester.toml` and sets `paths.suites = "suites"`.

jevtester finds suites, question sets, and policies relative to its config file: `suites/<name>.yaml`, `suites/question-sets/<name>.yaml`, and `suites/policies/<name>.yaml`. It also writes its run database to `.jevtester/`, which `.gitignore` lists. `uv run --project` doesn't change the working directory, and jevtester reads `./jevtester.toml` by default. So every jevtester command the app runs passes the config path explicitly, as the server the app starts does:

```sh
uv run --project ~/repos/jevtester jevtester --config ~/repos/ironsworn-tui/jevtester.toml serve --port <free port>
```

## Moves

### Moves the chat can trigger

The app sorts the 35 moves into four groups:

- **Triggered from the fiction**, which go in the `move` question's options: Face Danger, Secure an Advantage, Gather Information, Heal, Resupply, Make Camp, Undertake a Journey, Reach Your Destination, Compel, Sojourn, Draw the Circle, Forge a Bond, Test Your Bond, Swear an Iron Vow, Fulfill Your Vow, Forsake Your Vow, Enter the Fray, Strike, Clash, Battle, and Write Your Epilogue.
- **Offered after a result**, which the app offers as a key on the roll card: End the Fight, after a strong hit on Strike or Clash against a foe with progress marked. The disambiguation guide says not to call End the Fight on a fresh foe, so the card offers it only when the foe's track has at least one full box (4 ticks).
- **Triggered by an outcome**, which the app runs when a result calls for one: Pay the Price, Endure Harm, Endure Stress, Companion Endure Harm, Face Death, Face Desolation, Out of Supply, and Face a Setback.
- **Started by the player with a command**: Turn the Tide, Ask the Oracle, Reach a Milestone, and Advance.

Turn the Tide isn't a separate action. Its text says the character steals initiative "to make a move (not a progress move)", adds +1, and takes +1 momentum on a hit, or must Pay the Price on a miss. So `/tide` arms it for the next move. The app allows it once per fight, only when the foe has initiative, and treats the next attack as Strike.

Aid Your Ally is co-op only and is left out.

### Contexts

The option list depends on the context, and each context has a fixed list so that its jevtester suite matches what play sends:

| Context | When | Options |
|---|---|---|
| `exploring` | No fight, no journey | Every fiction move except Strike, Clash, Battle, and Reach Your Destination |
| `journey` | A journey is active, no fight | The `exploring` options plus Reach Your Destination |
| `fight` | A fight is active, whether or not a journey is | `attack`, Battle, Face Danger, Secure an Advantage, Gather Information, Compel, Heal, and Forsake Your Vow |

Every context adds `no_move` (the action has no risk, so nothing triggers) and `cannot_tell`. `exploring` has 19 options, `journey` 20, and `fight` 10. All three are under Clef-flash's limit of 26 on Ollama.

In the `fight` context, Strike and Clash are one option, `attack`. Code picks Strike when the character has initiative and Clash when the foe has it. Both moves offer iron in close quarters and edge at range, so they share one stat question.

## Questions per turn

One request contains every question for the turn:

| Id | Type | What it asks | Options from |
|---|---|---|---|
| `move` | choice | Which move the action triggers | The context's move list, each move described by a short criterion written from the disambiguation guide |
| `stat_<move>` | choice | Which approach the action takes, for that move | That move's `player_choice` conditions with text, each condition's text as the description, plus `cannot_tell` |

Stat questions go only to moves with two or more `player_choice` conditions that have text: Face Danger, Secure an Advantage, Battle, Compel, Enter the Fray, and `attack`. Because the move isn't known until the answer comes back, the request contains a `stat_<move>` question for each of those moves in the context. The app reads the one for the move the player confirms. Other moves have one stat, and code handles the rest:

- **Heal** rolls wits when the character treats someone else, and the lower of iron and wits when they mend their own wounds (`method: lowest`). The roll card asks the player which with a key.
- **Moves with `method: highest`** (Endure Harm, Endure Stress, Companion Endure Harm) use the higher value, which code computes.

The build step 4 experiment compares two kinds of `move` criteria: the short ones from the guide, and the Datasworn trigger text ("When you attempt something risky..."). The plan uses whichever scores better.

The state is JSON with the character's situation and the player's text:

```json
{
  "character": "Kira, a hunter",
  "circumstances": "Kira is on a journey, and no fight is under way.",
  "situation": "Pinned behind a cart. Two raiders with bows hold the ridge above the road.",
  "player_says": "I creep along the ditch to get behind the ridge where they can't see me."
}
```

`situation` is a scene line the player keeps up to date with `/scene`, plus the names of any active foes and journey. `circumstances` is a sentence code writes from the context and initiative. The model never sees the context id or a null initiative, because decision models read field names and do better with sentences than with coded values. [Decision model guidance](decision-model-guidance.md) gives the sources for this and for the question wording.

## Calling the decision model

`decide.py` starts `jevtester serve --port <free port>` once, with `--config` set to this repository's `jevtester.toml`, and sends each request to `POST /api/decide`. jevtester handles the Foundry, Workers AI, Ollama, and MLX targets and their sign-ins, so this app stores no credentials. A target that fails returns a result with `ok: false`, and the app then shows the full move list.

Build step 3 measured the alternative, a `jevtester decide` subprocess per call: it added 0.72 to 0.75 seconds to each call, over the half-second limit. Through the server, a warm call added about 13 milliseconds.

## Acting on the answers

The thresholds are a jevtester policy, `suites/policies/moves.yaml`, so `jevtester run` measures them along with accuracy. The policy has a band for `move` with `act` and `confirm` thresholds, a `per_target` section, and one rule per option that maps the answer to an action with the move's id. jevtester's confidence for a choice is `(p_max - 1/n) / (1 - 1/n)`, where `n` is the number of options.

The app reads the same policy file:

- **At or above `act`:** the suggestion bar preselects the move, and Enter rolls.
- **Between `confirm` and `act`:** the bar shows the top two moves, and the player picks one.
- **Below `confirm`, or no usable answer:** the bar shows the full list for the context. That covers a target that failed or timed out, a missing or unknown `move` answer, and a `DecideError` when jevtester can't be reached.
- **`no_move` or `cannot_tell` wins:** the message goes into the log with no roll. The player can still pick a move from the list.

Start with `act = 0.7` and `confirm = 0.4`, then tune them per target from the cases.

## Applying outcomes

`outcomes.py` describes, for each chat move and each hit (strong, weak, miss), what changes on the campaign. Datasworn's outcome text is prose, so this table is written by hand for the 21 chat moves, End the Fight, and the suffer moves, and tests check each entry against the move text. Each outcome is a list of effects:

- A change to momentum, health, spirit, or supply, limited by the meter's range and by debilities. A debility stops its meter from increasing, and the momentum maximum is 10 minus the number of debilities. The momentum reset is +2 with no debilities, +1 with one, and 0 with two or more.
- Progress marked on a vow, a journey, or a foe. A foe's progress per harm depends on its rank: 12 ticks for troublesome, 8 for dangerous, 4 for formidable, 2 for extreme, and 1 for epic. Harm is 1, and Strike's strong hit and Clash's "find an opening" option add +1.
- An initiative change. Strike's strong hit keeps initiative, its weak hit loses it, and any miss in a fight gives the foe initiative.
- A follow-up move: Pay the Price, Endure Harm with an amount, or Endure Stress with an amount. The harm a foe inflicts equals its rank (1 to 5).
- A player choice: "choose one" lists, Heal's supply-or-momentum cost, and Pay the Price's three options (choose, roll the oracle, or ask the oracle). The roll card numbers the choices, and the player picks.

When the outcome text says something the table can't express, the roll card shows the text and the player applies it with `/adjust`.

Rolls follow the rules in the reference:

- **Burning momentum** sets the action score to the momentum value against the same challenge dice, so the port re-evaluates the existing roll instead of rolling again. The roll card offers it only when it improves the result. Afterward, momentum resets.
- **A negative momentum** equal to the action die cancels the die.
- **Progress rolls** (End the Fight, Fulfill Your Vow, Reach Your Destination) ignore momentum and can't burn it.
- **A match** on the challenge dice is marked on the roll card. Ironsworn leaves its meaning to the player, so the app only shows it.

## Foes and fights

Enter the Fray asks the player for each foe's name and rank, with the NPC list from the Datasworn data as suggestions. Each foe has a progress track. When there's more than one foe, the player selects the target with `/target`, and an attack marks progress on that foe. End the Fight removes one foe, and the fight ends when no foes remain.

## The TUI

Use Textual. The screen has four parts:

- **Character panel** on the left: stats, health, spirit, supply, momentum, debilities, vows with progress, and any active foes or journey.
- **Log** on the right: the player's messages, rolls, and outcome text.
- **Suggestion bar**: the moves the policy offers, with probabilities, the suggested stat, and the key hints.
- **Input line** at the bottom.

Focus moves between the input line and the suggestion bar, so plain keys work in both:

- In the input line, Enter sends the message, and focus moves to the suggestion bar when the answers arrive. Text that starts with `/` is a command, not a message.
- In the suggestion bar, Enter rolls, 1 to 9 picks a move, e, h, i, s, and w change the stat, + and - change the add, and Escape returns to the input line without rolling.
- On the roll card, number keys pick an outcome choice, b burns momentum, and f offers End the Fight.

Commands:

| Command | Action |
|---|---|
| `/oracle <table>` | Roll an oracle table and show the raw result |
| `/ask <likelihood>` | Ask a yes/no oracle question: almost certain, likely, 50/50, unlikely, or small chance |
| `/vow` | Swear, mark progress on, fulfill, or forsake a vow |
| `/scene <text>` | Replace the situation text |
| `/target <foe>` | Select the foe an attack targets |
| `/tide` | Arm Turn the Tide for the next move |
| `/adjust <meter> <amount>` | Change a meter, a debility, or a progress track by hand |
| `/moves` | Show the full move list for the context |

After a roll, the log shows the move name, the dice, the hit, and the outcome text from the move data. In outcome text, a link to another move looks like `[Endure Harm](datasworn:move:classic/suffer/endure_harm)`. Show each link as the move name.

Run the decision call in a Textual worker, so the screen stays responsive. Decision-1 answered in about 1 second and Clef-flash on Workers AI in 2 to 3 seconds when tested on 2026-10-24.

## Campaign state

A campaign is one JSON file in `campaigns/<name>.json`, written after every turn. It contains the character (stats, meters, momentum, debilities, assets, experience), vows and their progress, bonds, any active foes and journey, initiative, whether Turn the Tide was used, the situation text, and the turn log. Pydantic models define it, and the file has a `schema_version`.

Character creation is a short form: a name, stats assigned from 3, 2, 2, 1, 1, three assets picked from the list, and a background vow. Your Truths worldbuilding is out of scope for the first version.

## jevtester cases

Every chat message the model answered is a test case, with three suites, one per context: `suites/play-exploring.yaml`, `suites/play-journey.yaml`, and `suites/play-fight.yaml`. Each suite uses a question set for its context in `suites/question-sets/` and the `moves` policy.

`cases.py` saves each turn with `jevtester case add --from-decide`, which reads the `decide` output the turn already has. The case's expected answers are:

- `move`: the move the player rolled, or `no_move` when the player pressed Escape without rolling.
- `stat_<move>`: the stat the player rolled with, for the move they rolled, when that move has a stat question.
- `expected_action`: the policy action for that move.

A case gets the `corrected` tag when the player overrode the model's top move. A turn where the request failed has no `decide` output, so it isn't saved.

To measure accuracy, run a suite and then report on the run:

```sh
uv run --project ~/repos/jevtester jevtester --config jevtester.toml run play-exploring --target decision-1@foundry --target clef-flash@workers-ai
uv run --project ~/repos/jevtester jevtester --config jevtester.toml report <run-id>
```

`jevtester probe` checks how much the answers depend on option order.

## Build order

Each step ends with a command that shows it works. Every step also passes the gates in the handoff.

1. **Scaffold and rules port.** Python 3.14 with uv, Textual, pydantic v2, and ruamel.yaml. Vendor the Datasworn data from osr-plugins commit `7e2e4a8` with its license file. Port `iron.py` into typed functions in `rules/` that return values and raise exceptions, and port `test_iron.py` to call them. Done when the gates pass and the ported tests cover action rolls, burning momentum, progress rolls, momentum bounds, suffer moves, and oracle rolls.
2. **Catalog and contexts.** A typed catalog over the moves, the four move groups, and the three context lists. Done when tests show each context's options, that every option is a real move id, and that the largest list has at most 26 options.
3. **Decision adapter.** Build the request, call jevtester with `--config`, and parse the answers into a typed result. Record jevtester JSON into `tests/fixtures/` and test against it. Put live calls behind `-m live`. Measure the subprocess startup time. Done when `uv run pytest` passes with fixtures and `uv run pytest -m live` gets an answer from `decision-1@foundry`.
4. **Recognizer experiment.** `uv run ironsworn-tui suggest "<text>" --context exploring` prints the suggested move and stat. Write 40 phrasings by hand for each context (120 in all) with expected moves and stats, covering every option and the ambiguities in the disambiguation guide. Write the question sets and the `moves` policy. Done when `jevtester report` gives accuracy for two targets and for both kinds of move criteria. Stop and review the numbers with the user before building the rest. If no target reaches 80 percent move accuracy on `exploring`, rework the criteria first.
5. **Outcomes, campaign, and turn loop.** `outcomes.py`, the pydantic models, JSON persistence, character creation, foes, and `turn.py`. Done when a test plays a scripted session with fixed dice and a fixture decision through `turn.py`: swear a vow, Face Danger, Enter the Fray against two foes, Strike, a miss that leads to Pay the Price, Turn the Tide, End the Fight, then save and reload, with the meters, progress, and initiative checked after each move.
6. **TUI.** The four-part screen, focus handling, the commands, the roll card, outcome choices, and momentum burn. Done when Textual's `run_test()` pilot, using a fixture decision, drives a turn from typing to an applied outcome, and a second test runs a `/` command.
7. **Case logging.** Save each turn with `jevtester case add`. Done when a scripted session through `turn.py` adds cases to the right suites, and `jevtester run` and `jevtester report` run on them.
8. **Assets.** Apply asset abilities that add to a roll or offer another stat. Ask the model whether an asset applies only once the app can apply it.

## Risks

- **Move recognition may be too weak.** Step 4 measures it before most of the app is built. The fallback is a full move list, so the app stays playable either way.
- **The outcome table is large.** 21 moves with three hits each, plus the follow-up moves. `/adjust` lets play continue when an entry is wrong, and tests compare each entry with the move text.
- **Answers may depend on option order.** Ollama gives ties to the first option. `jevtester probe` measures this.
- **The situation text may go stale.** If it doesn't reflect the scene, the model can't tell Face Danger from Secure an Advantage. The player updates it with `/scene`, and the log shows what was sent.
- **Calls take time.** One call per message, at 1 to 3 seconds each, may feel slow. A local model on Ollama would help once its download is done.
