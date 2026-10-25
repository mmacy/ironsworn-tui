# ironsworn-tui plan

ironsworn-tui is a terminal app for playing solo Ironsworn. The player types what their character does in a chat box. A decision model suggests which move that action triggers and which stat it uses. The player confirms the suggestion with a keypress, and the app rolls the dice and shows the move's outcome text.

The app has no LLM narrator. In solo Ironsworn the player writes the fiction, so the app only needs to recognize moves, roll dice, look up tables, and track the character.

## Goals

- Learn where decision models work well and where they don't, using real play as the test data.
- Recognize the triggered move from free text, and ask the player when the model isn't sure.
- Keep every roll deterministic and every rules decision in code or with the player, never with the model.
- Save every message and the move the player confirmed as a jevtester case, so accuracy can be measured and compared across models.

## Non-goals

- Narration, NPC dialogue, or oracle interpretation by a model.
- Co-op play, Ironsworn: Delve, and Ironsworn: Starforged.
- A web UI.

## Sources

| Source | What we take | Where |
|---|---|---|
| osr-plugins, Ironsworn referee plugin | `iron.py`, its tests, and the Datasworn YAML | `~/repos/osr-plugins/plugins/ironsworn-referee/skills/referee/`, commit `7e2e4a8` |
| Move disambiguation guide | The move criteria and the known ambiguities | `references/move_disambiguation.md` in the same folder |
| Play constitution | Which choices belong to the player | `references/constitution.md` in the same folder |
| jevtester | The `decide` command, suite and question set formats, and targets | `~/repos/jevtester` |

`iron.py` is a stateless CLI, and the app can import its functions directly. `action_roll()` takes the stat value, adds, and momentum, and returns the dice, the hit, whether a match occurred, and whether burning momentum would improve the result. `build_indices()` loads all 35 moves, the oracle tables, the 78 assets, the NPCs, the truths, and the rules into dictionaries keyed by id.

The Datasworn move data already contains the stat choices. For example, Face Danger's `trigger.conditions` lists five approaches, each with its stat ("With speed, agility, or precision" uses edge). The app builds its stat criteria from that data instead of writing them by hand. Each move also has a `roll_type`: `action_roll`, `progress_roll`, `special_track`, or `no_roll`.

## Licensing

The Datasworn files are CC BY 4.0 or CC BY-NC-SA 4.0, file by file. `iron.py` and the plugin's guides are CC BY-NC-SA 4.0. Vendor them with their `LICENSE.md`, and license this repository under CC BY-NC-SA 4.0 to match. The repository is private for now.

## Architecture

```text
ironsworn_tui/
  rules/       # vendored iron.py core and Datasworn data, plus a typed catalog over them
  moves.py     # which moves can trigger from chat in the current context
  decide.py    # builds the request, calls jevtester, parses the answers
  campaign.py  # pydantic models for the character, vows, fights, and journeys; JSON persistence
  turn.py      # one chat message from text to resolved move, with no UI code
  cases.py     # writes each turn as a jevtester case
  app.py       # the Textual app
```

`turn.py` contains the game loop and doesn't import Textual, so tests can run the loop without a terminal. The TUI is a thin layer over it.

### Moves the chat can trigger

Not every move belongs in the option list. The app sorts the 35 moves into three groups:

- **Triggered from the fiction**, which go in the option list: Face Danger, Secure an Advantage, Gather Information, Heal, Resupply, Make Camp, Undertake a Journey, Reach Your Destination, Compel, Sojourn, Draw the Circle, Forge a Bond, Test Your Bond, Swear an Iron Vow, Fulfill Your Vow, Forsake Your Vow, Enter the Fray, Strike, Clash, Turn the Tide, End the Fight, Battle, and Write Your Epilogue.
- **Triggered by an outcome**, which the app runs when a roll's result calls for one: Pay the Price, Endure Harm, Endure Stress, Companion Endure Harm, Face Death, Face Desolation, Out of Supply, and Face a Setback.
- **Started with a key**: Ask the Oracle, Reach a Milestone, and Advance. These are bookkeeping, so the model doesn't need to recognize them.

Aid Your Ally is co-op only and is left out.

The context then narrows the first group:

- **Strike and Clash** are one option, `attack`. Code picks Strike when the character has initiative and Clash when they don't.
- **Fight moves** (attack, Turn the Tide, End the Fight) appear only during a fight. Enter the Fray and Draw the Circle appear only outside one.
- **Reach Your Destination** appears only during a journey.
- **Turn the Tide** disappears once it's used in a fight.
- **End the Fight** appears only when the foe's progress track has at least one box filled.

Each context adds `no_move` (the action has no risk, so nothing triggers) and `cannot_tell`. The largest context has fewer than 26 options, which is Clef-flash's limit on Ollama.

### Questions per turn

One request contains every question for the turn:

| Id | Type | What it asks | Options from |
|---|---|---|---|
| `move` | choice | Which move the action triggers | The context's move list, each move described by its trigger text |
| `stat_<move>` | choice | Which approach the action takes, for that move | That move's `trigger.conditions`, each condition's text as the description, plus `cannot_tell` |
| `asset_<id>` | noul | Whether the action meets one of the character's asset abilities | One question per enabled asset ability that has a condition |

The stat choices differ by move. In the Datasworn data, Face Danger, Secure an Advantage, and Battle offer all five stats. Compel offers heart, iron, or shadow. Enter the Fray offers heart, shadow, or wits. Strike and Clash offer iron (close) or edge (ranged), and Heal offers wits or iron. The other moves have one stat or roll a progress track. Because the move isn't known until the answer comes back, the request contains one `stat_<move>` question for each move in the context that offers a choice. That's at most seven questions. The app reads the one for the move the player confirms. A request can contain up to 64 questions, so the extra questions cost only input tokens.

The state is JSON with the character's situation and the player's text:

```json
{
  "character": "Kira, a hunter",
  "situation": "Pinned behind a cart. Two raiders with bows hold the ridge above the road.",
  "in_fight": false,
  "on_journey": true,
  "player_says": "I creep along the ditch to get behind the ridge where they can't see me."
}
```

The `situation` field is the last few lines the player wrote, plus the name of any active fight or journey. The player can edit it with a key.

### Calling the decision model

`decide.py` runs `uv run --project ~/repos/jevtester jevtester decide --request - --target <target> --format json` as a subprocess and reads the JSON from stdout. jevtester already handles the Foundry, Workers AI, Ollama, and MLX targets and their sign-ins, so this app stores no credentials. The jevtester path and the target come from `ironsworn-tui.toml`.

The subprocess costs some startup time on each call. Measure it in build step 2. If it's more than half a second, run `jevtester serve` once and call its HTTP API instead.

### Acting on the answers

Each target has separate thresholds in `ironsworn-tui.toml`, because probabilities differ between models:

- **Confident:** the top move's probability is at or above `accept`, and it leads the second by at least `margin`. The suggestion bar preselects it, and Enter rolls.
- **Close call:** the top two are within `margin`. The bar shows both, and Enter does nothing until the player picks.
- **No move or unclear:** `no_move` or `cannot_tell` wins. The message goes into the log with no roll.
- **Request failed:** the bar shows the full move list for the context, and the player picks.

Start with `accept = 0.6` and `margin = 0.2`, then tune them from the cases.

## The TUI

Use Textual. The screen has four parts:

- **Character panel** on the left: stats, health, spirit, supply, momentum, debilities, vows with progress, and any active fight or journey track.
- **Log** on the right: the player's messages, rolls, and outcome text.
- **Suggestion bar**: the top moves with probabilities, the suggested stat, and the key hints.
- **Input line** at the bottom.

Keys:

| Key | Action |
|---|---|
| Enter | Accept the suggestion and roll |
| 1 to 9 | Pick a move from the bar |
| e, h, i, s, w | Change the stat |
| l | Show the full move list for the context |
| m | Burn momentum, when it would improve the result |
| o | Pick an oracle table and roll it |
| y | Ask a yes/no oracle question at a chosen likelihood |
| v | Vows: swear, mark progress, fulfill, forsake |
| x | Edit the situation text |

The input line keeps focus while the player types, so single-letter keys need a modifier or an empty input line. Settle the binding in build step 6.

After a roll, the log shows the move name, the dice, the hit, and the outcome text from the move data. In outcome text, a link to another move looks like `[Endure Harm](datasworn:move:classic/suffer/endure_harm)`. Show each link as the move name, and offer the linked move as the next action. When an outcome says "choose one", the log lists the options with numbers, and the player picks one.

Run the decision call in a Textual worker, so input stays responsive. Decision-1 answered in about 1 second and Clef-flash on Workers AI in 2 to 3 seconds when tested on 2026-10-24.

## Campaign state

A campaign is one JSON file in `campaigns/<name>.json`, written after every turn. It contains the character (stats, meters, momentum, debilities, assets, experience), vows and their progress, bonds, any active fight or journey, and the turn log. Pydantic models define it, and the file has a `schema_version`.

Character creation is a short form: a name, stats assigned from 3, 2, 2, 1, 1, three assets picked from the list, and a background vow. Your Truths worldbuilding is out of scope for the first version.

## jevtester cases

Every turn is a test case. `cases.py` writes each turn to `suites/play.yaml` with:

- The state that was sent.
- The `expected` move: the one the player rolled, or `no_move` when the player sent the message without rolling.
- `provenance: "human"`, since the player confirmed it.
- A `corrected` tag when the player overrode the model's top move.

A jevtester suite uses one fixed question set, but the move options change with the context. So the app writes one question set and one suite per context: `exploring`, `journey`, and `fight`. Each question set contains the `move` question and the `stat_<move>` questions for that context. Asset nouls vary by character, so they stay out of the suites.

Then `uv run --project ~/repos/jevtester jevtester run suites/play-exploring.yaml --target decision-1@foundry --target clef-flash@workers-ai` measures accuracy per target, and `jevtester probe` checks how much the answers depend on option order.

## Build order

Each step ends with a command that shows it works.

1. **Scaffold.** Python 3.14 with uv, Textual, pydantic v2, and ruamel.yaml. Vendor `iron.py`, its tests, and the Datasworn data from osr-plugins commit `7e2e4a8`, with their license file. Add the gates: `ruff format --check`, `ruff check`, `pyright`, and `pytest`. Done when `uv run pytest` passes the vendored `iron.py` tests.
2. **Rules catalog and move contexts.** A typed catalog over `build_indices()`, the three move groups, and the context filter. Done when tests show the option list for each context and that every chat-triggered move id exists in the data.
3. **Decision adapter.** Build the request, call jevtester, and parse the answers into a typed result. Use recorded jevtester JSON in `tests/fixtures/` for tests, and put live calls behind `-m live`. Done when `uv run pytest` passes with fixtures and `uv run pytest -m live` gets an answer from `decision-1@foundry`.
4. **Recognizer script.** `uv run ironsworn-tui suggest "<text>" --context exploring` prints the suggested move, stat, and assets. Write 40 phrasings by hand with expected moves, covering every chat-triggered move and the ambiguities in the disambiguation guide. Save them as the first `play-*` suites. Done when `jevtester run` reports accuracy for two targets. Stop and review the numbers before building the TUI. If no target reaches 80 percent on the exploring suite, rework the move criteria first.
5. **Campaign and turn loop.** The pydantic models, JSON persistence, character creation, and `turn.py`. Done when a test plays a scripted session with fixed dice through `turn.py`: swear a vow, Face Danger, Enter the Fray, Strike, End the Fight, and save and reload.
6. **TUI.** The four-part screen, the keys, the roll card, hit options, momentum burn, oracles, and vows. Done when Textual's `run_test()` pilot drives a turn from typing to a logged roll.
7. **Case logging.** Write each turn to the context's suite. Done when a played session produces cases that `jevtester suite check` accepts.

## Risks

- **Move recognition may be too weak.** Step 4 measures it before the UI is built. The fallback is a full move list, so the app stays playable either way.
- **Trigger text alone may describe moves poorly.** Datasworn's trigger text is written for people ("When you attempt something risky..."). The guide's short descriptions may work better. Step 4 can compare the two.
- **Answers may depend on option order.** Ollama gives ties to the first option. `jevtester probe` measures this.
- **The situation text may go stale.** If it doesn't reflect the scene, the model can't tell Face Danger from Secure an Advantage. The player can edit it, and the log shows what was sent.
- **Calls cost time.** One call per message, at 1 to 3 seconds each, may feel slow. A local model on Ollama would help once its download is done.

## Open questions

- Should the situation come only from the player's recent messages, or also from a short scene line the player keeps up to date?
- Should vows and bonds use the same Markdown files as the plugin, so a campaign can move between the two?
