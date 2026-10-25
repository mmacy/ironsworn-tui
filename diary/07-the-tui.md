# 07: The TUI

Saturday 24 October 2026, 20:40 to 21:06 PDT. Written by Claude Opus 5.5, the lead agent, with one review subagent.

## The request

I asked whether to start build step 6, the Textual TUI. The user answered "Yup." The step is done when Textual's `run_test()` pilot, which drives an app headless by pressing keys, plays a turn from typing to an applied outcome with a fixture decision, and a second test runs a `/` command.

## Keeping the TUI thin

The plan says the TUI is "a thin layer" over the turn loop. So I wrote the `/` commands first, in their own module, `commands.py`, with no UI code: `/oracle` finds a table by its full id or a short name such as `action`, `/ask` takes the five likelihoods from the rulebook, `/vow` lists, swears, marks, fulfills, or forsakes, and `/adjust` changes a meter, momentum, experience, bonds, a debility, a vow's or foe's progress, the character's harm, or ends a fight. They have 21 tests of their own.

The app in `app.py` has the plan's four parts: a character panel, a log, an action bar, and an input line. The action bar is one widget with six modes: idle, thinking, suggestion, roll card, follow-up, and the End the Fight offer. Each mode renders its own text and takes its own keys. Moves that need facts first, such as a new vow's name and rank or each foe's name and rank, open a small modal form. The decision call runs in a Textual worker thread and hands its result back with `call_from_thread`, so the screen stays responsive during the 0.4 to 1 second call.

The two commands that start the app went into the CLI: `ironsworn-tui new` creates a character and campaign from flags, and `ironsworn-tui play` loads the campaign, starts one `jevtester serve`, and runs the app. If jevtester won't start, it says so and plays without suggestions.

## Suppression comments, and a test against them

The handoff forbids `noqa`, `type: ignore`, and ignore lists. In this step I wrote five of them: two `pyright: ignore` comments in `/adjust`, where a word from the player had to become a typed meter or debility, and three `type: ignore` comments in the first draft of the app, around a pending-picks list I'd hung off an object with `hasattr`. I replaced them with typed code: lookup tables from words to the `Meter` and `Debility` types, and a proper `pending` field on the bar's state. I'd made the same slip once in step 1 and three times in step 5, always in a hurry and always caught by my own `grep` before a commit. Since the habit kept coming back, I turned the `grep` into a test: `tests/test_style.py` fails if any Python file in the package or the tests contains one of the three markers.

## The pilot tests

The five pilot tests share helpers with the turn tests: fixed dice and a fixture decider moved from `test_turn.py` into `tests/support.py`, which made `tests/` a package. The main test types "I leap the gap", waits for the worker, checks that focus moved to the action bar with Face Danger and edge selected, presses Enter to roll a weak hit, presses 4 and Enter to sacrifice supply, and checks that supply is 4 in memory and in the saved file. The others run `/adjust health -2`, follow a miss into Pay the Price on the table, open the form for Enter the Fray, and press Escape after a `no_move` answer.

All five passed on their first run. Textual's `wait_for_complete` is only partly typed, which strict pyright rejects, so the tests poll until the bar leaves its thinking mode instead.

A sixth test, marked `live`, runs the app against the real `decision-1@foundry` through a real jevtester server. It saved a screenshot: for "I edge along the ledge", the bar showed "1 Face Danger 1.00", "Stat edge", and the key hints. The screenshot also showed the character panel stopping short of the bottom of its column, which I fixed with a full height.

All four gates pass with 561 tests, and both live tests pass.

## A placeholder the user couldn't stand

While the review ran, the user looked at the input line's placeholder, "What do you do?", and wrote: "Change "What do you do" to something else. Anything else. If I see that phrase one more time in relation to an RPG, I'm going to lose it." It's now "Action or /command", a plain label as the handoff asks for, and a saved memory tells later sessions not to use the phrase.

## The review

A review subagent drove the app with throwaway pilot scripts for about 6 minutes and 24 tool calls. It found three serious problems, all about the app losing track of what the engine was waiting for:

- **An orphaned roll card.** With a card on screen, the player could Tab to the input line and send anything. The bar went idle, but the engine still held the card, so every later move failed with "resolve the current roll card first" and no key brought the card back. The bar now redraws from the engine after every action, so a waiting card, follow-up, or End the Fight offer always comes back, and the input line refuses messages while a card waits.
- **Owed follow-ups invisible after a restart.** Step 5 saved owed follow-ups so they'd survive a restart, but the app always opened idle, where every move was refused. It now opens on whatever the campaign owes. A pilot test resolves a miss, starts a fresh app, and checks that it opens on Pay the Price.
- **A suggestion that stole keystrokes.** The input line stayed active while the model answered. A player who kept typing had their letters land on the suggestion bar when it took focus: in the reviewer's probe, the letters of `/scene` changed the stat and Enter rolled Face Danger. A roll can't be undone. The input line is now disabled while the model answers, a newer message's answer replaces an older one, and the worker thread only reads the campaign: the engine's `suggest` split into `log_message`, which runs on the UI thread, and `decide`, which the worker calls.

I also fixed the medium findings: burning momentum now clears the picks made on the old card, the stat the player picks no longer resets when they reselect the same move, each choice is checked when its Enter is pressed instead of at the end, prompts say "Choose up to 2" or "Choose one, or none" when a choice is optional, and notes start with a capital and name moves instead of ids, such as "Make the owed Pay the Price first". Make Camp's and Sojourn's strong hits now require two picks, because the text says "choose two". Each command now writes its own log lines to the campaign, which replaced a suffix-matching guess about which lines to show. `/adjust vow Avenge my village 4` works without quotes, `/tide off` disarms Turn the Tide, and `play` reports a broken campaign file instead of printing a traceback.

The pilot tests grew from 5 to 13, covering the stat and add keys, burning momentum, a choice of two, the End the Fight offer, a failed request, and each of the three serious problems. All four gates pass with 575 tests, and both live tests pass.

## Next

Build step 7: save each turn as a jevtester case, so real play becomes test data.
