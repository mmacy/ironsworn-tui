# 09: The asset catalog and owning assets

Sunday 25 October 2026, 01:14 to 01:34 PDT. Written by Claude Opus 5.5, the lead agent, with one review subagent.

## The scope decision

Build step 8 is assets. In Ironsworn an *asset* is a card that gives the character a talent, a companion, a path, or a ritual. Each card has three abilities, and a new asset starts with one of them marked. Because stats run only from 1 to 3, assets do most of the work of making one character different from another.

I had offered two scopes: apply the simple abilities (a +1 or another stat) and show the rest as text, or do all 78 assets. The user said they doubted they'd come back to either later, and asked what skipping assets would cost. I listed what's missing today. The app never showed the three assets picked at creation. Bonuses work only if the player remembers to press `+`. "Roll +X instead" abilities can't be used at all, because the turn engine refuses a stat the move doesn't list. Rerolls, companions, rituals, and spending experience don't exist. The user decided: "Well I guess we should do all of it if we've come this far. Why not?"

## Reading all 234 abilities

Before designing anything, I dumped every ability's text, one line each, into a 47,780-byte file and read it all. Datasworn, the structured Ironsworn data the app vendors, encodes more than I expected:

- Which moves each ability enhances, such as `move:classic/combat/strike`. 203 abilities have at least one enhancement.
- Any stat or asset meter an ability lets a move roll instead. Archer's first ability lists wits and edge, and Commander's lists the warband's strength.
- The 23 moves that abilities add, such as each ritual's move, Craft Arrow, and Scrape By, with full trigger and outcome text.
- Meters (10 companion health meters, plus strength, essence, light, wealth, and the simulacrum's health), text fields such as a companion's name, and select fields such as a Devotant's god's stat.

It doesn't encode the bonuses themselves: "+1", "take +1 momentum on a hit", "inflict +2 harm", "reroll any dice". Those need a hand-written table. That shaped the plan, which now splits step 8 into four pull requests: the catalog and ownership, abilities on a roll, asset moves with lasting effects and companions, and finally the decision model. The last part changes the model's questions, so it needs its own experiment, and it starts only after the user agrees.

## The catalog

The asset YAML was loaded as untyped dictionaries until now. Part 1 adds strict pydantic models: `Asset`, `Ability`, `Enhancement`, `AssetMeter`, `AssetSelect`, and the 23 asset moves as ordinary `Move` models with the category `asset`. The asset moves go in their own index, not with the 35 core moves, because the decision model's questions are built from the core moves.

Enhancement ids come in two forms, `move:classic/combat/strike` and `asset.ability.move:classic/ritual/augur.0.augur`. Both reduce to a leaf id, `strike` or `augur`. One move Datasworn references, `check_your_gear`, isn't a classic Ironsworn move at all. Improviser's first ability names it; my reading is that the card was written for Ironsworn: Delve.

The ability text had Datasworn links in it, such as `[Endure Harm](datasworn:move:classic/suffer/endure_harm)`. The turn engine already had a `plain_text` function that reduces these to their labels, so I moved it next to the models and reused it.

All 14 catalog tests passed on the first run.

## Owning assets

The character's `assets` field was a list of ids. Now each owned asset records its three marks, its meter values, its filled-in fields, and whether it counts as a debility. The campaign file format went to version 2 with no migration, because no campaign files existed yet.

`/asset buy` spends 3 experience and `/asset upgrade` spends 2, as the Advance move says. Three path abilities take 1 off: Animal Kin for companions, Ritualist for rituals, and Weaponmaster for combat talents. Companions, Battle-scarred, and Shadow-kin start with no ability marked, so the player picks one, written `hawk:2` at creation.

Marking two abilities moves stat points once. Shadow-kin's first ability lowers heart by 1 and raises shadow by up to 2. Battle-scarred's first lowers edge or iron by 1 and adds 2 to wits or heart, or 1 to each. Both stop at 4. The player writes the changes as `/asset buy shadow-kin 1 -heart +shadow +shadow`, and the app checks them against the card. Battle-scarred's second ability lowers maximum health to 4 and stops maimed counting as a debility, so health now has a maximum that can change.

Assets that count as a debility lower maximum momentum like a marked debility: Oathbreaker always, and Commander at 0 strength. Ironclad's "geared for war" marks encumbered, as the card says, rather than counting the asset itself.

## The review

A review subagent took about 2.5 minutes and 15 tool calls, reproduced its first three findings in Python, and found three serious bugs:

- A new character created with `battle_scarred:2` kept 5 health against a maximum of 4, so `new` saved a file that `play` refused to load. Creation now sets health to the maximum.
- Discarding Battle-scarred made maimed count again, which could leave momentum over the new maximum and the file unloadable. Discarding now lowers momentum and health to their maximums.
- Animal Kin's discount applied to every companion, but the card says "animal or beast companion", and Kindred is a person. Kindred is now excluded.

It also found that Kindred's `expertise` field was dropped, because it's the only field an ability defines rather than the asset. Choosing lightly armored cleared encumbered even when it was marked for another reason. Nothing could record that Fated or Leech counts as a debility, so I added `/asset debility <asset> on|off`. Multi-word names such as "cave lion" failed, so the command now tries the longest run of words that names an asset. Shadow-kin couldn't be taken with shadow already at 4, though the card says "up to +2". The campaign check now also rejects an asset missing its starting mark, an Oathbreaker that doesn't count as a debility, and geared for war without encumbered.

I wrote a test for each finding first, then fixed it. The gates pass with 665 tests.

## Also in this pull request

When I reported step 7, I said diary entry 08's end time was wrong. It said 21:32, and the entry was written at 21:29. I corrected it, with a note in that entry.

Part 2 is next: the ability table and the turn engine's hooks for adds, other stats, momentum, harm, costs, rerolls, and result changes.
