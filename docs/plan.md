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

## Sources

| Source | What we take | Where |
|---|---|---|
| osr-plugins, Ironsworn referee plugin | The Datasworn YAML, and `iron.py` and its tests as the reference for the port | `~/repos/osr-plugins/plugins/ironsworn-referee/skills/referee/`, commit `7e2e4a8` |
| Move disambiguation guide | The move criteria and the known ambiguities | `references/move_disambiguation.md` in the same folder |
| Play constitution | Which choices belong to the player, and how initiative works | `references/constitution.md` in the same folder |
| jevtester | The `decide`, `run`, and `report` commands, the `serve` API for adding cases, the suite, question set, and policy formats, and the targets | `~/repos/jevtester` |

`iron.py` is a CLI, not a library. Only `action_roll()` and `build_indices()` return values. Progress rolls, suffer moves, oracles, and momentum bounds exist only as `cmd_*` functions that print JSON, and its error helper calls `sys.exit(2)`. It also fails this project's gates: ruff and pyright both report findings, and `test_iron.py` uses `# noqa` and runs `iron.py` as a subprocess. So `ironsworn_tui/rules/` holds the rules as typed functions, with the tests ported to call them, and uses `iron.py` as the reference for the math.

The Datasworn move data contains the stat choices. Each move's `trigger.conditions` lists its approaches, and each condition has a `method` (`player_choice`, `lowest`, or `highest`) and the stats it rolls with. For example, Face Danger lists five `player_choice` approaches ("With speed, agility, or precision" uses edge). Single-stat moves have a condition with no text. Each move also has a `roll_type`: `action_roll`, `progress_roll`, `special_track`, or `no_roll`.

## Licensing

The Datasworn files are CC BY 4.0 or CC BY-NC-SA 4.0, file by file. `iron.py` and the plugin's guides are CC BY-NC-SA 4.0, and the port is a derived work. The Datasworn data is vendored with its `LICENSE.md`, and this repository is licensed under CC BY-NC-SA 4.0 to match.

## Architecture

```text
ironsworn_tui/
  rules/        # typed port of iron.py: action and progress rolls, momentum, suffer moves, oracles, Datasworn models
  outcomes.py   # the effect of each move's outcome on the campaign
  moves.py      # which moves the chat can trigger in the current context
  criteria.py   # the descriptions of the `move` question's options
  decide.py     # builds the request, calls jevtester, parses the answers
  policy.py     # turns the answers into a suggestion with the policy's thresholds
  campaign.py   # pydantic models for the character, assets, vows, foes, and journeys; JSON persistence
  assets.py     # buying and upgrading assets
  abilities.py  # the hand-written table of what each asset ability and lasting effect does
  turn.py       # one chat message from text to applied outcome, with no UI code
  commands.py   # the `/` commands, with no UI code
  cases.py      # saves each turn as a jevtester case
  app.py        # the Textual app
```

[`architecture.md`](architecture.md) describes every module.

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
- **Offered after a result**, which the app offers as a key on the roll card: End the Fight, after a strong hit on any move made in a fight when the targeted foe's track then has at least one full box (4 ticks). The rulebook (page 82) allows any decisive move as the setup. The app doesn't offer it after Enter the Fray, Draw the Circle, Battle, a progress move, or a rolled suffer move, and the player declines the offer when the move wasn't decisive.
- **Triggered by an outcome**, which the app runs when a result calls for one: Pay the Price, Endure Harm, Endure Stress, Companion Endure Harm, Face Death, Face Desolation, Out of Supply, and Face a Setback.
- **Started by the player with a command**: Turn the Tide, Ask the Oracle, Reach a Milestone, and Advance.

Turn the Tide isn't a separate action. Its text says the character steals initiative "to make a move (not a progress move)", adds +1, and takes +1 momentum on a hit, or must Pay the Price on a miss. So `/tide` arms it for the next move. The app allows it once per fight, only when the foe has initiative, and treats the next attack as Strike.

Aid Your Ally is Secure an Advantage for an ally. It's on the full move list, not a `move` option, and rolls as Secure an Advantage with the benefits noted for the ally.

### Contexts

The option list depends on the context, and each context has a fixed list so that its jevtester suite matches what play sends:

| Context | When | Options |
|---|---|---|
| `exploring` | No fight, no journey | Every fiction move except Strike, Clash, and Reach Your Destination |
| `journey` | A journey is active, no fight | The `exploring` options plus Reach Your Destination |
| `fight` | A fight is active, whether or not a journey is | `attack`, Battle, Face Danger, Secure an Advantage, Gather Information, Compel, Heal, and Forsake Your Vow |

Every context adds `no_move` (the action has no risk, so nothing triggers) and `cannot_tell`. `exploring` has 20 options, `journey` 21, and `fight` 10. Battle is in all three, because it can replace a whole fight, including Enter the Fray (rulebook page 84). All three are under Clef-flash's limit of 26 on Ollama.

In the `fight` context, Strike and Clash are one option, `attack`. Code picks Strike when the character has initiative and Clash when the foe has it. Both moves offer iron in close quarters and edge at range, so they share one stat question.

## Questions per turn

One request contains every question for the turn:

| Id | Type | What it asks | Options from |
|---|---|---|---|
| `move` | choice | Which move the action triggers | The context's move list, each move described by a short criterion written from the disambiguation guide |
| `stat_<move>` | choice | Which approach the action takes, for that move | That move's `player_choice` conditions with text, each condition's text as the description. There's no `cannot_tell` option, because one won too often in the recognizer experiment. |

Stat questions go only to moves with two or more `player_choice` conditions that have text: Face Danger, Secure an Advantage, Battle, Compel, Enter the Fray, and `attack`. Because the move isn't known until the answer comes back, the request contains a `stat_<move>` question for each of those moves in the context. The app reads the one for the move the player confirms. Other moves have one stat, and code handles the rest:

- **Heal** rolls wits when the character treats someone else, and the lower of iron and wits when they mend their own wounds (`method: lowest`). The roll card asks the player which with a key.
- **Moves with `method: highest`** (Endure Harm, Endure Stress, Companion Endure Harm) use the higher value, which code computes.

`criteria.py` has two kinds of `move` criteria: the short ones from the guide, and the Datasworn trigger text ("When you attempt something risky..."). The guide criteria scored better in the recognizer experiment, so play uses them.

The state is JSON with the character's situation and the player's text:

```json
{
  "character": "Blarg, the Destructor",
  "circumstances": "Blarg is on a journey, and no fight is under way.",
  "situation": "Pinned behind a cart. Two raiders with bows hold the ridge above the road.",
  "player_says": "I creep along the ditch to get behind the ridge where they can't see me."
}
```

`situation` is a scene line the player keeps up to date with `/scene`, plus the names of any active foes and journey. `circumstances` is a sentence code writes from the context and initiative. The model never sees the context id or a null initiative, because decision models read field names and do better with sentences than with coded values. [Decision model guidance](decision-model-guidance.md) gives the sources for this and for the question wording.

## Calling the decision model

`decide.py` starts `jevtester serve --port <free port>` once, with `--config` set to this repository's `jevtester.toml`, and sends each request to `POST /api/decide`. jevtester handles the Foundry, Workers AI, Ollama, and MLX targets and their sign-ins, so this app stores no credentials. A target that fails returns a result with `ok: false`, and the app then shows the full move list.

A `jevtester decide` subprocess per call adds 0.72 to 0.75 seconds to each call, over the half-second limit. Through the server, a warm call adds about 13 milliseconds.

## Acting on the answers

The thresholds are a jevtester policy, `suites/policies/moves.yaml`, so `jevtester run` measures them along with accuracy. The policy has a band for `move` with `act` and `confirm` thresholds, and one rule per option that maps the answer to an action with the move's id. jevtester's confidence for a choice is `(p_max - 1/n) / (1 - 1/n)`, where `n` is the number of options.

The app reads the same policy file:

- **At or above `act`:** the suggestion bar preselects the move, and Enter rolls.
- **Between `confirm` and `act`:** the bar shows the top two moves, and the player picks one.
- **Below `confirm`, or no usable answer:** the bar shows the full list for the context. That covers a target that failed or timed out, a missing or unknown `move` answer, and a `DecideError` when jevtester can't be reached.
- **`no_move` or `cannot_tell` wins:** the message goes into the log with no roll. The player can still pick a move from the list.

`act` is 0.7 and `confirm` is 0.4. Tune them per target from the cases.

## Applying outcomes

`outcomes.py` describes, for each chat move and each hit (strong, weak, miss), what changes on the campaign. Datasworn's outcome text is prose, so this table is written by hand for the 21 chat moves, End the Fight, the suffer moves, and the asset moves, and tests check each entry against the move text. Each outcome is a list of effects:

- A change to momentum, health, spirit, or supply, limited by the meter's range and by debilities. A debility stops its meter from increasing, and the momentum maximum is 10 minus the number of debilities. The momentum reset is +2 with no debilities, +1 with one, and 0 with two or more.
- Progress marked on a vow, a journey, or a foe. A foe's progress per harm depends on its rank: 12 ticks for troublesome, 8 for dangerous, 4 for formidable, 2 for extreme, and 1 for epic. Harm is 2 for a character armed with a deadly weapon and 1 without one (rulebook page 19), stored on the character. Strike's strong hit and Clash's "find an opening" option add +1.
- An initiative change. Unless a move says otherwise, a strong hit in a fight takes or keeps initiative, and a weak hit or miss loses it (rulebook page 53). That includes suffer moves.
- A follow-up move: Pay the Price, Endure Harm with an amount, or Endure Stress with an amount. The harm a foe inflicts equals its rank (1 to 5).
- A player choice: "choose one" lists, Heal's supply-or-momentum cost, and Pay the Price's three options (choose, roll the oracle, or ask the oracle). The roll card numbers the choices, and the player picks.

When the outcome text says something the table can't express, the roll card shows the text and the player applies it with `/adjust`.

Rolls follow the rules in the reference:

- **Burning momentum** cancels each challenge die lower than the momentum, and any other die stands against the action score. The port re-evaluates the existing roll instead of rolling again. The roll card offers it only when it improves the result. Afterward, momentum resets.
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

- In the input line, Enter sends the message, and focus moves to the suggestion bar when the answers arrive. The input line is disabled while the model answers, so keys typed then can't reach the bar. Text that starts with `/` is a command, not a message. While a roll card is waiting, the input line takes nothing until the card is applied.
- In the suggestion bar, Enter rolls, 1 to 9 and then A to Z pick a move, e, h, i, s, and w change the stat, + and - change the add, and Escape returns to the input line without rolling.
- On the roll card, number keys pick an outcome choice, Enter confirms each choice and then applies the card, and b burns momentum. After a strong hit in a fight that leaves the target with a full box, the bar offers End the Fight with f, and Escape declines it.

Commands:

| Command | Action |
|---|---|
| `/oracle <table>` | Roll an oracle table and show the raw result |
| `/ask <likelihood>` | Ask a yes/no oracle question: almost certain, likely, 50/50, unlikely, or small chance |
| `/vow` | Swear, mark progress on, fulfill, or forsake a vow |
| `/scene <text>` | Replace the situation text |
| `/target <foe>` | Select the foe an attack targets |
| `/tide` | Arm Turn the Tide for the next move. `/tide off` disarms it. |
| `/adjust <meter> <amount>` | Change a meter, a debility, or a progress track by hand |
| `/moves` | Show the full move list for the context |

After a roll, the log shows the move name, the dice, the hit, and the outcome text from the move data. In outcome text, a link to another move looks like `[Endure Harm](datasworn:move:classic/suffer/endure_harm)`. Show each link as the move name.

Run the decision call in a Textual worker, so the screen stays responsive. Decision-1 answered in about 1 second and Clef-flash on Workers AI in 2 to 3 seconds when tested on 2026-10-24.

## Campaign state

A campaign is one JSON file in `campaigns/<name>.json`, written after every turn. It contains the character (stats, meters, momentum, debilities, assets, experience), vows and their progress, bonds, any active foes and journey, initiative, whether Turn the Tide was used, the situation text, and the turn log. Pydantic models define it, and the file has a `schema_version`.

`ironsworn-tui new` creates a character: a name, stats assigned from 3, 2, 2, 1, 1, three assets, up to three bonds, and a background vow. Your Truths worldbuilding is out of scope.

## jevtester cases

Every chat message the model answered is a test case, with three suites, one per context: `suites/play-exploring.yaml`, `suites/play-journey.yaml`, and `suites/play-fight.yaml`. Each suite uses a question set for its context in `suites/question-sets/` and the `moves` policy.

The engine saves each turn's case through the running `jevtester serve`, with `POST /api/suites/{name}/cases`, as soon as the player answers the message. The case's state is the one the model saw, and its expected answers are:

- `move`: the move the player made, or `no_move` when the player pressed `n` on the suggestion bar. Escape leaves the message without a move and saves no case, because it can also mean "not now".
- `stat_<move>`: the stat the player rolled with, for the move they rolled, when that move has a stat question.
- `expected_action`: the policy action for that move.

A case gets the `corrected` tag when the player overrode the model's top move, and the `abstained` tag instead when the model's top answer was `cannot_tell`. A turn where the request failed has no `decide` output, so it isn't saved. The play suites are tracked in git, because the user chose to keep them. `ironsworn-tui write-suites` creates them once and never rewrites them, because they hold the cases.

To measure accuracy, run a suite and then report on the run:

```sh
uv run --project ~/repos/jevtester jevtester --config jevtester.toml run play-exploring --target decision-1@foundry --target clef-flash@workers-ai
uv run --project ~/repos/jevtester jevtester --config jevtester.toml report <run-id>
```

`jevtester probe` checks how much the answers depend on option order.

## Assets

The user asked for every asset, not a subset. There are 78 assets with 234 abilities. Datasworn gives each ability's text, the moves it enhances, any stat or asset meter it lets a move roll instead, and the moves a ritual adds. It doesn't encode the bonuses themselves, such as +1, +1 momentum on a hit, +2 harm, or a reroll. Those come from a hand-written table in `abilities.py`, keyed by asset id and ability index, and a test checks every marked-ability text against its entry.

### Owning assets

- The character owns a list of assets. Each owned asset records which of its three abilities are marked, its meter values (a companion's health, a warband's strength), its text fields (a companion's name, a Devotant's god and stat), and its choice (Ironclad's armor).
- A new asset starts with the abilities Datasworn marks as enabled. Companions, Battle-scarred, and Shadow-kin start with none, so the player picks one.
- `/asset buy` spends 3 experience on a new asset, and `/asset upgrade` spends 2 to mark an ability, as Advance says. Animal Kin, Ritualist, and Weaponmaster take 1 off for their kind of asset.
- Marking some abilities changes the character once: Battle-scarred and Shadow-kin move stat points, and Battle-scarred lowers maximum health. The app applies these when the ability is marked.
- An asset can count as a debility: Oathbreaker always, Commander at 0 strength, Fated after its protection is used, Leech while the rune is unquenched, and Ironclad when geared for war (which marks encumbered). These lower maximum momentum like any debility.
- The character panel lists each asset with its marked abilities and meters.

### Abilities on a roll

- When the player picks a move, the app lists the marked abilities that enhance it. The player turns on the ones whose condition holds in the fiction, such as "by hunting". The app can't judge the fiction, so it never turns one on by itself.
- Each ability's entry says what it does: an add, a stat or asset meter to roll instead, momentum on a hit or strong hit, extra harm or a set amount of harm, a cost before rolling (supply, momentum, or an asset meter), a reroll of any dice, a weak hit counted as a miss or a strong hit as a weak hit, a choice of one of several effects, and a limit of once per fight or one time only.
- Some abilities act when something else happens rather than on a roll: on burning momentum (Swordmaster, Veteran, Banner-sworn, Wayfinder, Revenant), on marking experience for a vow (the +1 experience abilities), on filling a progress box (Bonded, Fated), or at Face Death (Owl). The turn engine calls the table at those points.
- A reroll is a new step on the roll card: the player picks which dice to roll again.
- What remains is text the player reads and applies with `/adjust`: envisioning, asking the oracle, and effects on allies, who don't exist in solo play.

### Asset moves and lasting effects

- 23 abilities add a move, such as each ritual's move, Craft Arrow, and Scrape By. The app adds them to the full move list once the character owns the ability, and the outcomes table gets an entry for each.
- Many results grant a lasting effect: an elixir, a bound pelt, a keen, a talisman, a blood rune, a ward. The campaign keeps a list of these. Each has the same kind of entry as an ability, and ends after one use, on an action die of 1, or when the player removes it. They appear in the same list as abilities when the player picks a move.
- Companion Endure Harm joins the suffer moves when the character has a companion. A companion at 0 health that dies is removed, and the character takes 1 experience for each marked ability.

### Asking the model

The model still sees only the core moves. Adding asset moves or ability conditions to its questions changes every question set, so it needs its own experiment first. That's the last part of build step 8, and it starts only after the user agrees.

## Build order

Each step ends with a command that shows it works. Every step also passes the gates in the handoff. Steps 1 through 8.3 are built, and step 8.4 is open.

1. **Scaffold and rules port.** Python 3.14 with uv, Textual, pydantic v2, and ruamel.yaml. Vendor the Datasworn data from osr-plugins commit `7e2e4a8` with its license file. Port `iron.py` into typed functions in `rules/` that return values and raise exceptions, and port `test_iron.py` to call them. Done when the gates pass and the ported tests cover action rolls, burning momentum, progress rolls, momentum bounds, suffer moves, and oracle rolls.
2. **Catalog and contexts.** A typed catalog over the moves, the four move groups, and the three context lists. Done when tests show each context's options, that every option is a real move id, and that the largest list has at most 26 options.
3. **Decision adapter.** Build the request, call jevtester with `--config`, and parse the answers into a typed result. Record jevtester JSON into `tests/fixtures/` and test against it. Put live calls behind `-m live`. Measure the subprocess startup time. Done when `uv run pytest` passes with fixtures and `uv run pytest -m live` gets an answer from `decision-1@foundry`.
4. **Recognizer experiment.** `uv run ironsworn-tui suggest "<text>" --context exploring` prints the suggested move and stat. Write 40 phrasings by hand for each context (120 in all) with expected moves and stats, covering every option and the ambiguities in the disambiguation guide. Write the question sets and the `moves` policy. Done when `jevtester report` gives accuracy for two targets and for both kinds of move criteria. Stop and review the numbers with the user before building the rest. If no target reaches 80 percent move accuracy on `exploring`, rework the criteria first.
5. **Outcomes, campaign, and turn loop.** `outcomes.py`, the pydantic models, JSON persistence, character creation, foes, and `turn.py`. Done when a test plays a scripted session with fixed dice and a fixture decision through `turn.py`: swear a vow, Face Danger, Enter the Fray against two foes, Strike, a miss that leads to Pay the Price, Turn the Tide, End the Fight, then save and reload, with the meters, progress, and initiative checked after each move.
6. **TUI.** The four-part screen, focus handling, the commands, the roll card, outcome choices, and momentum burn. Done when Textual's `run_test()` pilot, using a fixture decision, drives a turn from typing to an applied outcome, and a second test runs a `/` command.
7. **Case logging.** Save each turn as a case through the running jevtester server. Done when a scripted session through `turn.py` adds cases to the right suites, and `jevtester run` and `jevtester report` run on them.
8. **Assets**, in four pull requests:
   1. **Catalog and ownership.** Typed asset models, owned assets with marks, meters, and fields, `/asset` commands that spend experience, one-time changes from marked abilities, assets that count as debilities, and the panel. Done when a test buys and upgrades assets with experience and the campaign saves and loads them.
   2. **Abilities on a roll.** The ability table and the turn engine's hooks: adds, other stats, momentum, harm, costs, rerolls, result changes, limits, and the burn and experience hooks. Done when a test makes each kind of roll with an ability on and checks the result, and a test checks every enhancing ability has an entry.
   3. **Asset moves, lasting effects, and companions.** The 23 asset moves, their outcomes, the lasting effects list, and Companion Endure Harm. Done when a scripted session performs a ritual, uses its effect, and has a companion endure harm.
   4. **The model and assets.** An experiment on adding asset moves and ability conditions to the questions. Starts only after the user agrees.

## Risks

- **Move recognition may be too weak.** The recognizer experiment measures it. The fallback is a full move list, so the app stays playable either way.
- **The outcome table is large.** 21 moves with three hits each, plus the follow-up moves. `/adjust` lets play continue when an entry is wrong, and tests compare each entry with the move text.
- **Answers may depend on option order.** Ollama gives ties to the first option. `jevtester probe` measures this.
- **The situation text may go stale.** If it doesn't reflect the scene, the model can't tell Face Danger from Secure an Advantage. The player updates it with `/scene`, and the log shows what was sent.
- **Calls take time.** One call per message, at 1 to 3 seconds each, may feel slow. A local model on Ollama would help once its download is done.
