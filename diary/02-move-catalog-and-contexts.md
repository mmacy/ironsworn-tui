# 02: The move catalog and the three contexts

Saturday 24 October 2026, 18:44 to 18:51 PDT. Written by Claude Opus 5.5, the lead agent, with one review subagent.

## Step 1 lands

Step 1 merged as pull request #1 at 18:44. Merging with `gh pr merge --squash --delete-branch` also removed the local `scaffold` worktree, so the `git worktree remove` I ran afterward failed with "is not a working tree". Nothing was lost; the branch was already merged.

## What step 2 asks for

Build step 2 in the plan is "a typed catalog over the moves, the four move groups, and the three context lists". It's done when tests show each context's options, show that every option is a real move id, and show that the largest list has at most 26 options. Clef-flash on Ollama, one of the decision models the project will test, accepts at most 26 options per choice question.

The *contexts* exist because the decision model gets a fixed list of options with every message, and the list should only hold moves that make sense right now. Strike makes no sense outside a fight, and Reach Your Destination makes no sense without a journey. The plan defines three contexts:

- `exploring`: 17 moves, plus `no_move` and `cannot_tell`, for 19 options.
- `journey`: the same plus Reach Your Destination, for 20.
- `fight`: `attack`, Battle, Face Danger, Secure an Advantage, Gather Information, Compel, Heal, and Forsake Your Vow, plus the two extras, for 10.

`attack` stands for both Strike and Clash. In Ironsworn, which of the two you make depends only on who has *initiative*, meaning control of the fight: Strike when you do, Clash when your foe does. Code knows the initiative, so the model doesn't have to guess it.

## Typing the moves

In step 1 the moves stayed as raw YAML dictionaries. I surveyed the 35 moves' keys before writing models. Every move has `name`, `type`, `roll_type`, `trigger`, and `text`; 26 have `outcomes` with exactly `strong_hit`, `weak_hit`, and `miss`; and the 26 that have `trigger.conditions` use 11 distinct shapes of roll option. Most say `using: stat` with a stat, but Make Camp rolls `condition_meter: supply`, Write Your Epilogue rolls the `bonds_track`, three moves roll a `progress_track`, and Companion Endure Harm rolls an `asset_control` (the companion's health).

The new pydantic models are `Move`, `Trigger`, `Condition`, `RollOption`, `Outcome`, and `Outcomes`, with `Literal` types for stats, meters, roll types, and condition methods, so a typo in the data would fail at load time. `Datasworn.moves` now maps ids to `Move` objects, and each `Move` carries its own `id` and `category`, which replaced the separate `move_categories` index from step 1.

The roll type counts came out as 22 action rolls, 9 moves with no roll, 3 progress rolls, and 1 special track. My first test said 23 and 8; I had counted Aid Your Ally, which has no roll, as an action roll. The data was right and the test was wrong.

## The groups and contexts

`ironsworn_tui/moves.py` holds the plan's four groups as a `MoveGroup` enum: 21 fiction moves, 1 offered after a result (End the Fight), 8 triggered by outcomes, and 4 started by commands. Aid Your Ally, a co-op move, has no group. A test checks that the groups cover all 35 moves except Aid Your Ally, and another that every real move in a context is a fiction move.

## Stat questions

The plan sends a second kind of question for moves where the player picks an approach, such as Face Danger's "With speed, agility, or precision" (edge) or "With deception, stealth, or trickery" (shadow). The rule is: a move gets a stat question when it has two or more `player_choice` conditions with text. I compute this from the data instead of hard-coding the list, and the results match the plan's list: Face Danger, Secure an Advantage, Compel, Enter the Fray, and Battle, plus `attack`. Heal doesn't qualify, because its second condition, "Mend your own wounds", uses the `lowest` method: the roll card asks the player instead.

`attack` uses Strike's approach texts, "In close quarters" (iron) and "At range" (edge). Clash's texts are longer ("Exchange a volley at range, or shoot at an advancing foe"), but a test checks that both moves offer the same two stats in the same order.

The first version passed all four gates with 207 tests, 40 of them new.

## The review

A fresh subagent reviewed the change against the plan in about 2 minutes, with 10 tool calls. It confirmed that the groups, the three option lists, the stat question moves, and the attack mapping match the plan, and found nothing serious. Its findings were about how the code would hold up in steps 3 and 5, and I acted on most of them:

- **Models that drop data silently.** pydantic ignores unknown keys by default, and most fields had defaults. If a Datasworn update renamed `roll_options` to `rollOptions`, every condition would have loaded with no roll options, and every stat question would have disappeared without an error. The move models now forbid unknown keys, and the loader removes the three keys the app doesn't use (`type`, `_source`, `oracles`) before validating. `RollOption` became a *discriminated union*, a type where the `using` field decides which of five models applies, so a stat option without a stat now fails to load. A validator also checks two rules that hold for all 35 moves: a move has outcomes exactly when it rolls, and a move names a progress track exactly when it makes a progress roll.
- **A dropped field.** I hadn't modelled `tracks`, which says which kind of progress track (journey, combat, or vow) Reach Your Destination, End the Fight, and Fulfill Your Vow roll on. Step 5 would have needed a hard-coded map without it.
- **Global state.** `stat_choices` read the cached data directly, while the rules modules take the data as a parameter, which lets tests pass in changed data. It and `move_group` now take a `Datasworn` argument, and `move_group` raises for an unknown id, so a typo like `"strik"` no longer looks like "a move the app leaves out".
- **Option order.** The plan says each context's list is fixed so that its jevtester suite matches what play sends, but my tests compared sets. A new test pins each list's exact order.
- **A helper for step 3.** `resolve_option(option, initiative)` turns a `move` answer into a move id: `attack` becomes Strike or Clash, and `no_move` and `cannot_tell` become no roll.

I left one suggestion for later: moving the `Initiative` type out of `moves.py` when step 5 builds the campaign state that also needs it. The reviewer also noticed that the plan's architecture listed a "catalog" under `rules/`, which no longer matched the code, so I changed the plan's wording to "Datasworn models".

After the fixes, all four gates pass with 265 tests.

## Next

Build step 3: the decision adapter, which builds a jevtester request from a context and the player's text, calls `jevtester decide`, and parses the answers. I've read jevtester's API document to prepare. A request has a `state` and named questions, and a choice answer comes back with a `probabilities` map and a `confidence` of `(p_max - 1/n) / (1 - 1/n)`.
