# 11: Asset moves, lasting effects, and companions

Sunday 25 October 2026, 02:00 to 02:24 PDT. Written by Claude Opus 5.5, the lead agent, with one review subagent.

## The 23 asset moves

Part 3 makes the moves that asset abilities add work like core moves. Each ritual has one, such as Augur ("When you summon a flock of crows and ask a single question"), and six other assets do too: Fletcher's Craft Arrow, Sunderer's Carve Rune, Alchemist's Create Elixir, Dancer's Commemorate, Outcast's Scrape By, and Pretender's Establish False Identity.

They don't join the decision model's questions, which would change every question set; that's part 4. They join the full move list (`/moves`) once the ability is marked, and the list the bar shows when the model isn't sure. The outcomes table got an entry for each, written from its result text, and the existing tests that compare amounts and follow-ups with the move text now cover them too. Those tests read the move's own text, and an asset move's text leaves out its miss, so the "Pay the Price" check failed for all of them until the helper read the result text as well.

Most rituals' second abilities say "As above, and ...", changing the result. The outcome functions now get a flag for whether the asset's second ability is marked: Bind offers a beast's pelt for +2, Ward's options improve to +2 momentum, +2 harm, and "almost certain", Keen adds a one-time bonus, and Alchemist lets one dose hold two effects.

## Lasting effects

Many results last: a talisman adds +2 when the wearer opposes its target, an elixir adds +1 to moves with one stat, a Seeker arrow allows one reroll. The campaign now keeps a list of these, and each kind has an entry in a table of 31 kinds, with a boost like an ability's and a rule for when it ends:

- 16 end after one use, such as an arrow or Shadow Walk's reroll.
- 8 end when the action die is a 1 on a move that used them ("the magic is spent"), such as a pelt or a talisman.
- 6 end when the player removes them with `/effects end`, such as a false identity.
- The elixir ends when health, spirit, or momentum falls below +1.

They appear in the same picker as abilities. Two abilities that used to be notes now start one: Dancer's audience (+2, one time only) and Giant Spider's reflection (a reroll on Gather Information).

My first version removed a used-up effect by its index and then, after the roll, looked up effects to expire by their indexes. Removing the first effect shifts every index after it, so the second lookup could find the wrong effect. I noticed before testing and changed both to work from the effect objects, captured before anything is removed.

## Companions and the suffer moves

Companion Endure Harm follows rulebook page 94: the harm comes off the companion's health, anything left over comes off momentum, and the roll uses heart or the companion's health, whichever is higher. On a miss with a 1 on the action die at 0 health, the companion dies; the character takes 1 experience for each marked ability and the asset is removed. `/asset harm hawk 2` owes the move. Make Camp's and Sojourn's recuperate options now heal companions, and Heal can treat a companion, named in the form.

Face Death and Face Desolation had outcome entries since step 5, but nothing triggered them. Two rows of the Endure tables call for them without a condition: "The harm is mortal. Face Death." and "You are overwhelmed. Face Desolation." Rolling either now owes the move. The rows that call for Face Death only under a condition, such as "If you are vulnerable to a foe not inclined to show mercy", stay as text for the player. With these reachable, the abilities that boost Face Death work too: Fated's automatic strong hit, Raven's +2, Owl's health as momentum, Masked's and Shadow-kin's other stats.

All of these, with Scrape By, go through one engine method, `roll_follow_up`, which replaced `endure`. Outcast's Scrape By triggers when supply drops to 0, in place of Out of Supply.

The first run of the new tests had two failures. One test's harm overflowed the foe's 40-tick track, so I lowered the numbers. The other was a real bug: Fated's automatic strong hit on Face Death still rolled dice. The test's dice queue had none loaded, so the roll failed. Automatic hits on a follow-up now skip the roll.

## Commands

`/effects` lists the lasting effects and `/effects end <n>` ends one. `/asset use lorekeeper` browses the forbidden archive, one time only: it raises wits by 1, rolls an action die, and on 1 to 3 tells the player to mark corrupted or Face Desolation. `/asset use slayer ritual` or `sojourn` takes a trophy.

The plan's done criterion is a scripted session that performs a ritual, uses its effect, and has a companion endure harm. The test fashions a talisman on a strong hit, uses it on Face Danger, loses it on an action die of 1, and has the hawk take 2 harm and rally. The gates passed with 890 tests.

## The review

A review subagent took about 4.5 minutes and 18 tool calls, reproduced its first five findings in a scratch script, and found two serious bugs:

- An owed Companion Endure Harm for a companion that had since died, or been discarded, could never be made, and no other move can be made while a follow-up is owed, so play was stuck for good. Rider's second ability could cause the same by owing harm to a horse the character doesn't have. Such an owed move is now dropped with a note, and Rider's boost needs the horse.
- A companion's death was added to the card once, after the first roll, so a reroll or a burn rebuilt the card without it, and a reroll that newly rolled a 1 never killed the companion. The death check moved into the card builder.

The smaller findings: Alchemist's "two doses of the same effect" couldn't be chosen, because a choice can't pick one option twice, so there are now "Two doses" options. Two lasting effects of one kind, such as two talismans, stacked to +4. The blood rune and the ward's harm applied to any move, but the text says "a move to inflict harm". Pelts and elixirs were offered on progress rolls. When a visage's magic was spent on a Strike, only its attack half ended. An elixir ended only when a roll was resolved, not when `/adjust` or Pay the Price lowered a meter. A save with an unknown lasting kind loaded and then crashed, so the engine now refuses it, and `play` reports it.

I wrote a test for each finding first. The gates pass with 900 tests.
