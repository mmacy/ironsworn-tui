# 06: Outcomes, the campaign, and the turn loop

Saturday 24 October 2026, 20:10 to 20:40 PDT. Written by Claude Opus 5.5, the lead agent, with one review subagent.

## The request

After entry 05 I asked the user whether to start build step 5. The reply was one word: "Engage."

Step 5 builds the game underneath the TUI: what each move's result does to the character, the campaign file, and the loop that takes one chat message through to an applied outcome. It's done when a test plays a scripted session through the loop with fixed dice and a fixture decision: swear a vow, Face Danger, Enter the Fray against two foes, Strike, a miss that leads to Pay the Price, Turn the Tide, End the Fight, then save and reload, checking meters, progress, and initiative after each move.

## Reading the rules first

I dumped the full text of the 32 moves the table has to cover into one file and read it before writing any code: the 21 moves the chat can trigger, End the Fight, Turn the Tide, the suffer moves, and Reach a Milestone. The plan's rule on debilities said only that "a debility stops its meter from increasing", so I checked the rulebook through the user's shelf-of-holding corpus. Page 37 is specific: "If you are wounded, you cannot increase health. If you are shaken, you cannot increase spirit. If you are unprepared, you cannot increase supply." The other five debilities lower maximum momentum and the reset but block no meter.

## The campaign model

`campaign.py` holds pydantic models for the character, progress tracks, foes, the log, and the campaign, with `extra="forbid"` so a misspelled field in a saved file fails to load. The context comes from the state instead of being stored: a fight while foes remain, a journey while one is active, otherwise exploring. Removing the last foe ends the fight, which clears initiative and resets Turn the Tide. Saving writes to a temporary file and then renames it over the old one, so a crash mid-write can't leave a half-written campaign.

## The outcome table

`outcomes.py` turns each move's result into a tuple of effects. There are 16 effect types: momentum, meter changes, progress, initiative, follow-up moves, clearing a debility, marking one, rolling a table, an add for the next move, experience, completing a vow, recommitting to a track, ending a journey, removing the targeted foe, a choice, and a `Note` for outcome text the effects can't express. The Note is the plan's escape hatch: the roll card shows the text, and the player applies it with `/adjust`. Draw the Circle's "To the death" boast, for example, is a Note.

Choices stay with the player, as the plan requires. Face Danger's weak hit is a `Choose` of its four costs, and Make Camp's strong hit is a `Choose` with a count of two. The table never picks for the player.

The tests check the table against the move text mechanically. For every momentum or meter amount anywhere in an entry, including inside choices, the test looks for the same phrase, such as "+2 momentum", in that move's text. Three amounts are derived instead of quoted, such as Resupply's "+2 supply for -2 momentum", which comes from "take up to +2 supply, but suffer -1 momentum for each". Those three are listed by name. Every follow-up move in an entry must also be named in the text.

## The turn loop

`turn.py` has a `TurnEngine` with no Textual import. A turn is a fixed sequence of calls: `suggest` sends the message to the decision model and returns what the suggestion bar offers; `make_move` rolls the confirmed move and returns a roll card; `burn` optionally burns momentum; `resolve` applies the card's effects with the player's choices and returns the follow-up moves; and `endure` and `pay_the_price` handle those follow-ups. A small `policy.py` reads the `act` and `confirm` thresholds from the jevtester policy file, so the app and the experiment use the same numbers.

Some rules live in the loop rather than the table, because they cut across moves: any miss in a fight gives the foe initiative; Turn the Tide adds +1, gives +1 momentum on a hit, and adds Pay the Price on a miss; supply falling to 0 marks unprepared (Out of Supply); and momentum lost past -6 becomes a Face a Setback note. Endure Harm and Endure Stress apply the damage before the roll, as entry 01's port does, and on a miss at 0 the card offers marking each unmarked debility of the pair (wounded or maimed, shaken or corrupted) or rolling on the move's table.

## The scripted session

The session test uses a `Dice` class that hands out queued rolls and fails if a roll is missing or off the die, and a fixture decider that builds a jevtester response for a chosen move and stat. Kira the hunter swears to find her brother (strong hit, momentum 2 to 4), edges along a ledge as the model suggested at 0.95 (weak hit; she sacrifices supply, 5 to 4), ambushes a raider chief and an archer (strong hit, momentum 6, initiative), strikes the chief twice (16 ticks, then a miss that costs initiative and rolls 45 on Pay the Price: "A new danger or foe is revealed."), turns the tide with a +1 Strike at range (32 ticks, momentum 7), and ends the fight with 8 boxes against 3 and 7. The saved file reloads equal to the campaign in memory.

All 13 turn tests passed on their first run, and all four gates passed with 505 tests. That turned out to say more about the tests than the code.

## The review

A review subagent spent about 7.5 minutes and 29 tool calls on the step, and wrote a probe script that drove the engine into each failure it suspected. It found seven serious problems that the 505 passing tests had missed. I checked the two rules claims against the rulebook myself before acting on them.

- **Initiative was wrong outside attacks.** I had coded only "any miss in a fight gives the foe initiative", from the plan. Rulebook page 53 says that unless a move says otherwise, "When you score a strong hit, you take or retain initiative. When you score a weak hit or miss, you lose initiative", and that this "applies even to suffer moves". A strong hit on Endure Harm after a failed Clash takes initiative back. The loop now applies that rule whenever a move's effects don't set initiative themselves.
- **Harm was half what the rules give.** The plan said "Harm is 1". Page 19 says: "If you are armed with a deadly weapon (such as a sword, axe, spear, or bow), you inflict 2 harm." Kira carries a bow. The character now has a `harm` field, 2 by default. In the scripted session her first strong Strike now marks 24 ticks on the dangerous chief instead of 16, and the Turn the Tide Strike fills the track to 40.
- **End the Fight could be rolled at any time.** The card computed an offer, but `make_move("end_the_fight")` never checked it. The offer now lives on the campaign, is set only when an attack's strong hit leaves the target with a full box, and clears on the next move.
- **End the Fight's weak hit took harm from the wrong foe.** The "It's worse than you thought" follow-up looked up the targeted foe's harm when Endure Harm ran, after the beaten foe had already left the fight. An extreme foe's 4 harm became the next foe's, or 1. Follow-ups now carry their amount from the moment the result creates them.
- **A Forsake Your Vow follow-up jammed the queue.** Nothing ever removed it, so every later follow-up failed. There's now a `forsake` method for it.
- **Required choices could be skipped.** An empty choice list passed, so a Face Danger weak hit could cost nothing. `Choose` now has a minimum, which is 0 only for Draw the Circle's optional boasts, and all choices are checked before any effect applies.
- **A refused move left the campaign half-changed.** Enter the Fray without a stat added the foes before it noticed the missing stat, which put the campaign in a fight that was never rolled, where Enter the Fray is no longer an option. Every check now runs before the campaign changes, and a test compares the campaign before and after a refused move.

I acted on most of the medium findings too. Options that a marked condition blocks are left off the card: rulebook page 37 says "If a move gives you an opportunity to raise your health, spirit, or supply while the associated condition is marked, you can't take that option." Resupply is refused while unprepared. Owed follow-ups, Turn the Tide, the next move's add, and the End the Fight offer moved into the saved campaign, so a restart doesn't drop an owed Pay the Price. No new move can be made while a follow-up is owed. Pay the Price gained its third way, asking the oracle at likely odds. Forge a Bond's and Test Your Bond's weak hits became choices, because whether the player did what was asked is the player's call. The plan now cites the rulebook for harm, initiative, and burning momentum.

The reviewer also found that my check of the table against the move text was too loose: it looked for each amount anywhere in the move's text, so swapping Gather Information's strong-hit and weak-hit momentum would have passed. It now checks each amount against the text of its own result.

Some gaps stay open and are listed in the handoff: Face Death and Face Desolation can't yet be triggered from a table result, Companion Endure Harm waits for assets, and a rolled but unresolved card is lost on restart.

All four gates pass with 531 tests.

## Next

Build step 6, the TUI.
