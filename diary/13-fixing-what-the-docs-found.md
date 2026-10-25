# 13: Fixing what the docs found

Sunday 25 October 2026, 06:58 to 07:16 PDT. Written by Claude Opus 5.5, the lead agent.

## The request

Entry 12 ended with a list of problems the documentation agents found and I didn't fix. I reported them to the user, who answered: "Fix those problems." Midway through, the user also asked for screenshots, a Zensical publishing pipeline to GitHub Pages, and to make the repo public "if it's ready". I handed the site and screenshots to a subagent in its own worktree, and a public-readiness audit to another. Entry 14 covers those.

## The six fixes

- **Harm from the fiction.** Pay the Price and a foe's attack only logged a cost, so the player took harm with `/adjust health` and skipped the Endure Harm roll. The new `/endure harm|stress <n>` command owes Endure Harm or Endure Stress, which the follow-up bar then rolls. The app still can't tell from the fiction that a character is hurt, so the player says so.
- **The End the Fight offer.** Escape hid the offer, but `end_fight_offered` stayed true, so the offer came back after any `/` command. Escape now calls `TurnEngine.decline_end_fight`.
- **Duplicate assets.** `new --assets archer,archer,wright` was accepted. `create_character` now refuses it.
- **Background bonds.** The rulebook says to start "with up to three background bonds" and "mark up to three ticks" (printed page 36). `new` takes a repeatable `--bond`, and each one marks a tick and logs `Bond: <text>`.
- **Settings errors.** A bad `ironsworn-tui.toml` ended in a Python traceback. `load_settings` now raises `SettingsError` with a short reason, such as "targett isn't a setting", and `cli.main` prints `Error:` and exits with 2.
- **The empty-choice note.** Enter on a choose-one card with nothing picked said "Choose 1 to 1". It now repeats the card's prompt, "Choose one".

## Aid Your Ally

Aid Your Ally had been left out as co-op only. Its Datasworn entry has `roll_type: no_roll` and no outcomes, because it modifies Secure an Advantage: "When you Secure an Advantage in direct support of an ally, and score a hit, they (instead of you) can take the benefits of the move." Adding it to the decision model's `move` options would change every question set, which is the step 8 part 4 experiment the user declined. So I added a fifth move group, `MoveGroup.LIST`, for moves picked only from the full list. Aid Your Ally rolls with Secure an Advantage's stats. On a hit, its outcome is a note for the ally, and on a miss it owes Pay the Price. Loyalist 1 changed from a reminder to a boost: +1, and +1 momentum on a hit.

## What the review caught

A review subagent found three bugs in the diff. The first was a rules error. I had let Secure an Advantage boosts apply to Aid Your Ally, but their benefits went to the player. The rulebook, page 76, says the ally "also takes those benefits (instead of you)". `boost_effects` now takes `for_ally`. For a Secure an Advantage boost on Aid Your Ally, its hit benefits become the note "Your ally also takes the benefits of <boost>", and its costs stay. Spirit-bound's Endure Stress on a weak hit is one such cost. The other two bugs were smaller. `/endure` typed while the move list showed left the list up, with every move refused. A settings file that wasn't UTF-8 still raised a traceback. All three now have tests, and the count went from 903 to 934.
