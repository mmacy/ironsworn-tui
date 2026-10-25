# 05: Two targets and the abstain options

Saturday 24 October 2026, 19:26 to 20:10 PDT. Written by Claude Opus 5.5, the lead agent.

## The user's review

At the end of entry 04 I stopped, as the handoff says, and asked the user three things. On the 120 cases: "Spot-checked a few, they look good to me. Ship it." On adding `clef-flash@workers-ai` as a second target: "Yeah, ad it." On reworking the stat questions and testing the companion yes/no question before step 5: "Agreed."

The user also asked whether the Battle gap from entry 04 was in our design or in Ironsworn. It's ours. Rulebook page 84 lets Battle replace a whole fight, Enter the Fray included, and our context table offered Battle only once a fight had started. Battle is now an option in `exploring` and `journey` too, which makes those lists 20 and 21 options long. A Battle case replaced one Face Danger case in each, so each context still has 40.

## Approving the cases

Approval meant changing one constant, `PROVENANCE`, from `claude-draft` to `human`, and regenerating the suites. jevtester now runs the suites directly, so there's no scratch copy anymore. A test now checks that every case is marked `human`.

## Four ways of asking

To compare request shapes, `build_request` gained a `RequestShape` with two switches: whether the stat questions offer `cannot_tell`, and whether a yes/no question named `acts` replaces the `move` question's `cannot_tell` option. The experiment code generates one suite per context for each of four variants: the two criteria styles, the stat questions with `cannot_tell`, and the `acts` question. The `acts` variant has its own policy, `moves-acts`, whose first rule turns a no on `acts` into `cannot_tell`. Twelve suites, 40 cases each, on two targets made 960 requests. They took a few minutes and cost $0.0288 on Workers AI; jevtester has no price for Foundry.

## What the numbers said

| Variant | Decision-1 move | Decision-1 stat | Clef-flash move | Clef-flash stat |
|---|---|---|---|---|
| guide, no stat `cannot_tell` | 115/120 | 58/59 | 107/120 | 56/59 |
| trigger, no stat `cannot_tell` | 112/120 | 58/59 | 101/120 | 56/59 |
| guide, stat `cannot_tell` | 115/120 | 53/59 | 108/120 | 54/59 |
| guide, `acts` question | 110/120 | 53/59 | 84/120 | 51/59 |

Three decisions followed, and play now uses them:

- **Drop the stat `cannot_tell` option.** It raised stat accuracy on both targets: Decision-1 from 53 to 58 of 59, Clef-flash from 54 to 56. A player can always change the stat with a key on the suggestion bar, so the model doesn't need a way to abstain.
- **Keep the `move` question's `cannot_tell` option.** TypeSafe's docs say a companion yes/no question "usually works better than a 'none of the above' option", but here it was worse on both targets. It caught the messages with no action, and also said no to real ones. Decision-1 gave a yes-probability of 0.22 to "The wyvern is dead. My vow to avenge my brother is done." and 0.11 to "Rocks crash down and raiders leap out at us from both sides! I grab my sword and shout for the guards." Clef-flash said no to 26 real actions, with every one between 0.14 and 0.50, so it was rarely sure either way. My reading is that "Does `player_says` describe something the character does?" is a harder question than it looks: declarations and reactions don't read as "doing".
- **Use the guide criteria.** They beat the Datasworn trigger text by 3 cases on Decision-1 and 6 on Clef-flash. In the first run the trigger text was 2 cases ahead on Decision-1 alone, so the first run's difference was noise, as entry 04 suspected.

I changed `RequestShape`'s defaults to the winning shape and renamed the variants to keep the old shapes reproducible: `guide-stat-forced` became the default `guide`, and the old `guide` became `guide-stat-abstain`. Rerunning the renamed suites confirmed the renaming: jevtester served the new `guide` suites and the `guide-stat-abstain` suites entirely from its cache, because their requests were byte-for-byte the same as before. Only the `trigger` suites, whose requests changed, were sent again. The rename also left six stale files on disk, because `write-suites` writes files but never deletes them, so a new test fails when a recognizer file exists that the generator wouldn't write.

## The second target

Clef-flash cleared the 80 percent bar on `exploring` at 87.5 percent, with Decision-1 at 95. Its calibration is weaker: its expected calibration error was 0.19 to 0.23, against 0.03 to 0.05 for Decision-1. With the same `act` and `confirm` thresholds, its policy escalated 5 to 17.5 percent of cases to the full move list, where Decision-1's escalated none. Its median latency was 531 to 652 ms through jevtester, against 445 to 483 ms for Decision-1.

One question from the research stayed open. Clef's reference code decides all questions in a request jointly, so the stat questions might change the `move` answer. Removing the stat `cannot_tell` option changed one `move` choice on Clef-flash and none on Decision-1. But the probability of the chosen move shifted by up to 0.09 on both models, so either Decision-1 isn't strictly independent either, or the hosted models vary from run to run. One run of each can't tell those apart; `--repeats` could.

## Verification

All four gates pass with 340 tests, and the live test passes against `decision-1@foundry`. `experiments/results.md` has both runs, the per-context numbers, and what's still unmeasured: option order, the `character` field, the top-two ratio, and run-to-run variation.

## Next

Build step 5: outcomes, the campaign model, and the turn loop.
