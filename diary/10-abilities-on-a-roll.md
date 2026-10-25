# 10: Asset abilities on a roll

Sunday 25 October 2026, 01:36 to 01:59 PDT. Written by Claude Opus 5.5, the lead agent, with two review subagents.

## The table

Part 2 of the assets work makes the abilities do something when a move is rolled. Datasworn says which moves an ability enhances, but not what it does to them, so every ability needs a hand-written entry. The table in `abilities.py` has 234 entries, one per ability, of three kinds:

- 180 abilities give *boosts*: things the player turns on before rolling, because their condition holds in the fiction. Some have alternatives, such as Archer's "Trust your instincts" (+wits, +2 momentum on a strong hit) and "Line up your shot" (+edge, +1 momentum on a hit). There are 223 boosts in all.
- 23 abilities add a move, such as each ritual's. Part 3 writes their outcomes.
- 31 abilities are *reminders*: the app doesn't apply them, and the entry says why. Some apply when the ability is marked, as Shadow-kin's stat change does. Some affect an ally, which solo play doesn't have. Eleven mention part 3, which will handle them.

The app never turns a boost on by itself. It can't tell whether the character is "hunting" or "embodying your wild nature", so the player decides.

A boost is a frozen dataclass with 41 fields, because the abilities do many different things. Besides adds and momentum there are: rolling another stat or an asset meter, extra harm or a set harm, costs before rolling, rerolls (after any result, only after a miss, or one challenge die), adds after rolling, counting a weak hit as a miss, automatic strong hits, effects on an action die of 1, effects when momentum is burned, extra experience on Fulfill Your Vow, extra options on Make Camp, limits of once per fight or one time only, and a few single-use fields such as Lightbearer's unleashed light.

My first draft of the table had a shorthand function that passed keyword arguments through to the dataclass, with a `pyright: ignore` comment to quiet the type checker. The project forbids that comment, and a test fails on it. I replaced every call with the typed constructor before running the gates.

## Checking the table against the data

A test compares each boost with the Datasworn enhancements for its ability: the moves it names must be ones the data enhances, and any stat it rolls must be one the data offers. The first run found 13 mismatches. I read each card, and every one was a gap in the data rather than in the table. Thunder-Bringer's third ability, for example, enhances Turn the Tide in the data, but its text says "you may Strike with all the fury and power you can muster", so the boost is on Strike. The test lists each exception with a quote from the card.

While I wired the table into the engine, a subagent read all 234 entries against the card text, in about 2 minutes and 9 tool calls. It found seven problems. I fixed five:

- Horse's charge and Raven's trickery each left out a stat. In the data, one enhancement covers both moves, and I'd given the stat to only one.
- Fortune Hunter's "add +wealth and suffer -1 wealth" would add one less than the card says if the engine paid the cost before reading the meter. The engine reads it first, and the field's docstring says so.
- Slinger's "Hit them hard" paid its momentum before rolling. The cost goes with the hit, so it moved to `on_hit`.
- Oathbreaker's redemption says "you *may* then improve one of your stats by +1 and discard this asset", but the entry forced the choice. It's optional now.
- Shield-Bearer's sacrifice was limited to once per fight, but the card limits only the initiative it gives. The shield is destroyed anyway, so I dropped the limit.

I didn't take its suggestion to make Waterborn's "Make Camp now" and Giant Spider's "Gather Information" into owed follow-ups. The engine refuses every other move while a follow-up is owed, and only Endure Harm, Endure Stress, Pay the Price, and Forsake Your Vow can settle one, so an owed Make Camp would block play. They stay as notes.

## The engine

`make_move` and `endure` take the boosts the player turned on, check that each can be used, and only then change the campaign: record a limited use, pay the costs, and roll. A roll card now carries its own result, because a boost can count a weak hit as a miss, and burning momentum afterwards keeps the downgrade. Three new steps can follow a roll: `reroll` rerolls the dice the player picks, `late_add` takes an add after rolling and its cost, and `burn` can now cancel one die of a progress roll, for Revenant's End the Fight.

Some abilities act on things that aren't rolls. Filling a box on the bonds track gives Bonded's experience and momentum. Reach a Milestone, which `/vow mark` now goes through, gives Fated's experience for every two boxes on the background vow, and ends Fated's debility. The campaign records the background vow's name for this.

In the TUI, `a` opens a picker of the boosts that apply to the selected move, or to an owed Endure Harm or Endure Stress roll. On the roll card, `r` opens a dice picker and `+` takes the add after rolling.

The first run of the engine tests had five failures, and all five were in the tests. Three had dice where the score tied a challenge die, such as 8 against 8, and a tie is a miss in Ironsworn. One expected the wrong error message, and one expected the mask's cost already turned into spirit on the card, which happens only when the card is applied.

## The engine review

A second subagent reviewed the engine and TUI changes for about 4.8 minutes and 29 tool calls, reproduced its first four findings with scratch scripts, and found four serious bugs:

- A once-per-fight boost used outside a fight was recorded, and only the end of a fight cleared the record, so the boost stayed unavailable in every later fight. A move made outside a fight now clears the record first, so a use on Enter the Fray still counts for the fight it starts.
- On Endure Harm, a weak hit counted as a miss (Berserker's third ability) at 0 health skipped the choice of marking a debility or rolling on the table, because that check read the dice's result rather than the counted one.
- On Endure Harm, Fortune Hunter's "add +wealth" took the wealth and added nothing, because only `make_move` read the meter. Both paths now share one helper.
- On Endure Harm, Masked's +1 applied without checking that the roll used the mask's stat.

It also found that a boost that only changes an action roll, such as an add, was offered and charged on progress moves like Fulfill Your Vow, where it does nothing. Revenant's End the Fight boost couldn't be reached from the TUI, because the End the Fight offer took no `a` key. Saves made before this change had no background vow, so they now take the first vow. Veteran took initiative when burning turned the dice's miss into a weak hit even if a boost still counted it as a miss. The picker took only keys 1 to 9, so it now continues with letters. Boosts picked before `/tide` stayed on after Attack changed from Strike to Clash, so commands now clear them.

I wrote a test for each finding first. One of my new tests was wrong: it checked that no `SetInitiative` effect appeared after the burn, but a Strike miss always has `SetInitiative("foe")`. It now checks for the character's initiative only, and a second test checks that Veteran still takes initiative when it should.

The gates pass with 747 tests.
