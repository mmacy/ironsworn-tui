# How Ironsworn plays in ironsworn-tui

ironsworn-tui applies most of the rules of *Ironsworn* for you, and leaves the story and the choices to you. You don't need to have played Ironsworn before, but finish [Getting started](getting-started.md) first.

For step-by-step tasks, like running a fight or buying an asset, see [How-to guides](how-to.md). For every command and key, see the [Reference](reference.md).

## The rulebook

*Ironsworn* is a tabletop roleplaying game by Shawn Tomkin. You can play it solo, with no game master. The rulebook is a free download from the publisher, Tomkin Press, at [tomkinpress.com](https://tomkinpress.com/products/ironsworn-digital-edition). The page numbers below are the numbers printed on the rulebook's pages. In the PDF, add 11 to find the same page.

## What the app decides and what you decide

The app and you split the work this way:

- **You decide the story.** In the game, the story is called the *fiction*. You decide what your character does, what the world looks like, and what a result means.
- **A decision model suggests a move.** A *decision model* is a small AI model that reads what you type and guesses which move it triggers. It only suggests. You confirm or override it.
- **The app applies the rules.** It rolls the dice, works out the result, changes your meters and progress tracks, and keeps track of the moves you owe.
- **You make every choice a result offers.** When a move says "choose one," the app lists the options and you pick.

The app never decides fiction for you. It can't see the story, so it can't tell whether you're in a community, whether your foe is a beast, or whether the price you pay should be an injury. Where a rule depends on the fiction, the app asks you or leaves it to you.

## The fiction-first loop

Ironsworn is played *fiction first*. You describe what your character does. If the action is risky or uncertain, it triggers a *move*. A move is a rule with a trigger, like Gather Information's "When you search an area, ask questions, conduct an investigation, or follow a track" (rulebook page 62). Each move lists what to roll and what each result means. If an action isn't risky, no move triggers, and it happens.

In the app, a turn goes like this:

1. You type what your character does and press Enter.
2. The decision model reads it and suggests a move. The suggestion bar shows the move, with the model's confidence after each name.
3. You confirm the move, pick another one, or say no move applies.
4. The app rolls and shows a *roll card*: the move, the result, and any choices.
5. You make the choices, and the app applies the result.
6. If the result calls for another move, like Endure Harm, the app asks you to make it next.

The log records each turn, so you can learn the rules as you play. The first time you make a move, the log says what the move is for. Then it shows the roll, the result's text from the rulebook, the options you picked, and each change with its new value, like "Momentum +2 (now 4)." When the result calls for something the app can't do, a line that starts with "Next:" says what it is. For example, Gather Information's strong hit says to envision what you learn, so the log says "Next: imagine what you learn and type it, or ask the oracle." "Envision" is the rulebook's word for imagining what happens in the story.

How much the suggestion bar offers depends on the model's confidence:

- **Confident:** The bar selects one move. Press Enter to roll it.
- **Less sure:** The bar shows the two likeliest moves, with the first selected.
- **Unsure:** The bar shows the full move list, with nothing selected, and you pick.
- **No move:** If the model thinks no move applies, or can't tell, the bar says "No move" and lists the moves, with nothing selected. Press `n` to agree, or pick a move.

If a move lets you choose a stat, the model also suggests one. You can change it with a stat key. You can also add a bonus with `+` and `-` before you roll. `/moves` shows every move you can make now, including moves your assets add.

The moves on offer depend on where you are. Outside a fight and a journey, you get the exploring moves. During a journey, you can also Reach Your Destination. In a fight, you get Attack, Battle, and a few others, like Face Danger and Secure an Advantage. Attack becomes Strike or Clash depending on who has initiative (see [Fights](#fights)).

To play without the model, start the app with `--no-model`. The suggestion bar then shows the full move list for every message. [How-to guides](how-to.md) shows how.

The app saves each message the model answered as a test case, with the move you chose. Together, the cases show how often the model is right. If you press Escape to leave a message without a move, the app saves no case for it.

## The action roll

Most moves use an *action roll* (rulebook pages 8 and 9). You roll three dice:

- The *action die*: one six-sided die (d6).
- The *challenge dice*: two ten-sided dice (d10).

Your *action score* is the action die plus a stat plus any *adds*. An add is a bonus, like +1 from a move or an asset. The action score can't be more than 10. You compare the action score with each challenge die. To beat a die, the score must be higher. A tie counts as not beating it.

| Your action score beats | Result | What it means |
|---|---|---|
| Both challenge dice | Strong hit | You succeed. |
| One challenge die | Weak hit | You succeed, but with a cost or a lesser effect. |
| Neither challenge die | Miss | You fail, or pay a serious price. Something always happens. |

The app rolls the dice, adds everything, and shows the result on the roll card. The log shows the full roll, for example "4 + 2 + 1 = 7 vs 3, 9, weak hit."

### Matches

A *match* is when both challenge dice show the same number (rulebook pages 9 and 10). In solo play, a match is a prompt to add a twist. On a strong hit, the twist is usually an opportunity. On a miss, things get worse in an unexpected way.

The app adds "match" to the roll in the log. A match doesn't change the result. You decide what the twist is, or ask the oracle (see [Oracles](#oracles)).

## Stats

Your character has five *stats*, each from 1 to 3 at the start (rulebook page 33):

- **Edge:** quickness, agility, and skill in ranged combat.
- **Heart:** courage, willpower, empathy, sociability, and loyalty.
- **Iron:** physical strength, endurance, aggressiveness, and skill in close combat.
- **Shadow:** sneakiness, deceptiveness, and cunning.
- **Wits:** expertise, knowledge, and observation.

Each move sets which stat you roll, or lets you choose one by how you act. With Face Danger, for example, you roll edge if you act with speed and iron if you act with force. The model suggests a stat, and you can change it. You know how your character acted, so the choice is yours.

## Health, spirit, and supply

You have three *meters*, each from 0 to 5 (rulebook pages 33 and 34):

- **Health:** your physical condition. It drops when you Endure Harm.
- **Spirit:** your mental state. It drops when you Endure Stress.
- **Supply:** your food, gear, and ammunition. It drops on journeys and as a cost.

The app changes the meters when a result says to. The character panel shows them.

When supply reaches 0, the app makes the Out of Supply move for you: it marks the *unprepared* condition (rulebook page 97). If you lose more supply while unprepared, you must take that loss from health, spirit, or momentum instead. The app logs a note, and you choose where the loss goes and apply it with `/adjust`.

## Momentum

*Momentum* shows how well things are going (rulebook pages 11 to 14). It runs from -6 to +10. Your character starts at +2 (rulebook page 35). Moves give momentum when things go your way and take it when they don't.

### Burning momentum

When your momentum is positive, you can *burn* it after a roll. Burning cancels each challenge die that is lower than your momentum. A cancelled die counts as beaten. So if both dice are lower, you get a strong hit. If one is lower, the other die still stands against your action score.

After you burn, your momentum resets. The *reset* value is +2, or less if you have debilities (see below).

The app's rule is that burning can only help. The roll card shows "b burn momentum" only when burning would give a better result than the dice did. A challenge die that burning doesn't cancel still counts against your action score, so burning never makes a result worse. You decide whether to burn. You might save momentum for a more important roll.

You can't burn momentum on a progress roll (see [Progress tracks](#progress-tracks)). One asset ability, Revenant's "Bring death," is an exception.

### Maximum momentum and negative momentum

Your maximum momentum is 10, minus 1 for each debility you have marked. The character panel shows your momentum with its current maximum and reset.

When your momentum is negative and equals your action die, the action die counts as 0. The app does this for you, and the log says "action die cancelled."

### Face a Setback

Momentum can't go below -6. If you lose momentum when you're already at -6, you must Face a Setback (rulebook page 97). You either take the extra loss from health, spirit, or supply, or you lose progress on a quest, journey, or fight.

The app logs a note with the amount, whether you lost the momentum to a move or to `/adjust momentum`. You choose how to pay it and apply it with `/adjust`.

## Conditions and debilities

A *debility* is a lasting disadvantage, like a wound (rulebook pages 36 to 38). Each marked debility lowers your maximum momentum by 1. One debility lowers your reset to +1, and two or more lower it to 0. The app tracks all of this.

The four *conditions* are debilities that come and go:

- **Wounded:** You can't gain health.
- **Shaken:** You can't gain spirit.
- **Unprepared:** You can't gain supply.
- **Encumbered:** You carry too much.

While a condition is marked, the app leaves out any choice that would raise the matching meter. Some moves clear a condition. A hit on Heal, for example, clears wounded.

Other debilities are permanent, like *maimed* or *corrupted*. The app marks a debility when a result calls for it. To mark or clear one yourself, use `/adjust`.

## Progress tracks

Some challenges are too big for one roll. In Ironsworn, you track them on a *progress track*: ten boxes that you fill as you make headway (rulebook pages 14 to 18). Each box has four *ticks*.

### Ranks

Vows, journeys, and foes each have a *rank*. The rank sets how much one mark of progress fills.

| Rank | One mark of progress fills |
|---|---|
| Troublesome | 3 boxes |
| Dangerous | 2 boxes |
| Formidable | 1 box |
| Extreme | 2 ticks |
| Epic | 1 tick |

You choose the rank. A harder challenge is slower to finish. The app marks the right amount for the rank.

### Progress moves

A *progress move* settles a challenge. It uses a *progress roll*: you count your fully filled boxes and compare that number with the two challenge dice. There's no action die, and momentum doesn't count (rulebook page 18). The results are the same as an action roll's.

The four progress moves are Fulfill Your Vow, Reach Your Destination, End the Fight, and Write Your Epilogue. You don't have to fill a track before you roll. You decide when you're ready to take the risk.

### Vows

A *vow* is a sworn quest, like "Avenge my village." Vows drive the game (rulebook pages 4 and 98 to 101).

- **Swear:** When you swear a vow, you make the Swear an Iron Vow move. The app asks for the vow and its rank. You can type the oath as fiction, or use `/vow swear`. Your character's first vow, the *background vow*, comes from character creation.
- **Mark progress:** When you overcome an important obstacle in your quest, you Reach a Milestone and mark progress. The app can't tell when that happens, so you decide and use `/vow mark`.
- **Fulfill:** When you think the quest is done, you make Fulfill Your Vow. On a strong hit, the app marks experience by the vow's rank and clears the vow. On a weak hit, it marks one less. On a miss, you choose to recommit or give up the vow.
- **Forsake:** If you give up a vow, you Forsake Your Vow. The app clears the vow and makes you Endure Stress equal to its rank.

`/vow` lists your vows and their progress.

### Journeys

When you travel through dangerous land, you Undertake a Journey (rulebook pages 65 to 68). The app asks for the destination and rank, and starts a journey track. Each hit marks progress on it. When you arrive, you Reach Your Destination, a progress move. The app ends the journey on a hit. On a miss, you choose whether the journey continues.

### Fights

A fight starts with Enter the Fray (rulebook pages 78 to 89). You name each foe and give it a rank. Each foe gets a progress track. A foe's rank also sets how much harm it deals: 1 for troublesome, up to 5 for epic.

Whoever has *initiative* is in control. With initiative, you act. Without it, you react. The app tracks it and shows it on the character panel. Unless a move says otherwise, a strong hit in a fight takes initiative, and a weak hit or a miss loses it (rulebook page 53).

When you attack, the suggestion bar offers Attack. With initiative, Attack is Strike. Without it, Attack is Clash. Each hit marks progress on the targeted foe's track. With more than one foe, `/target` picks which foe you attack.

How much harm you deal depends on your weapon. A deadly weapon, like a sword, axe, spear, or bow, deals 2 harm. An improvised or simple weapon deals 1. The app uses the harm you set when you created the character. Change it with `/adjust` if your weapon changes.

To win the fight, you make End the Fight, a progress move on the foe's track. On a strong hit, the foe is out of the fight. The app removes it. On a weak hit, you also choose a cost.

Turn the Tide lets you seize initiative once per fight when the foe has it (rulebook page 81). You add +1 to the move and take +1 momentum on a hit. On a miss, you must Pay the Price. `/tide` sets up Turn the Tide for your next move.

Battle settles a whole fight with one roll, if you don't want to play out each exchange.

A fight can also end without End the Fight, for example when you flee or the foe surrenders. Use `/adjust` to end it.

#### When the app offers End the Fight

The rulebook lets you make End the Fight after any strong hit on a move meant as a decisive action (rulebook page 82). Only you know whether a move was meant that way. So the app offers End the Fight after a strong hit on any move you make in a fight, like Strike, Clash, Face Danger, or Secure an Advantage. The bar shows "f end the fight." Press Escape to keep fighting when the move wasn't decisive.

The app doesn't offer it after Enter the Fray, Draw the Circle, or Battle, after a suffer move like Endure Harm, or when the targeted foe has no full box of progress. With no full box, End the Fight can't score a hit.

#### Draw the Circle

Draw the Circle starts a duel (rulebook page 73). On a strong hit, you can choose up to three boasts, and on a weak hit, one. The app applies each boast:

- **Grant first strike:** Your foe has initiative.
- **Bare yourself:** Your foe's harm is +1 until the fight ends. End the Fight's "It's worse than you thought" cost, and `/endure harm` with no amount, use the higher harm.
- **Hold no iron:** Your harm is 1 until the fight ends. The app then sets it back to what it was.
- **Bloody yourself:** You owe Endure Harm for 1 harm.
- **To the death:** The app logs it. You decide what it means in the fiction.

### Bonds

A *bond* is a close tie to a person or community (rulebook page 36). When you Forge a Bond, the app marks one tick on your bonds track. Some moves add +1 when you share a bond with someone. The app can't tell whether you do. For Sojourn, the app asks: answer `yes` in the Bond field, and the app adds the +1 and lets you choose one more recovery option on a hit (rulebook page 71). Don't also add the +1 yourself. For other moves, like Compel or Draw the Circle, add the +1 yourself with `+` before you roll. When your character retires, you roll Write Your Epilogue against your bonds track.

The rulebook lets you start with up to three background bonds. Name them with `--bond` when you create your character, and the app marks a tick for each. To add a bond later, use `/adjust bonds`.

### Aid Your Ally

Aid Your Ally is Secure an Advantage made in direct support of an ally (rulebook page 76). On a hit, your ally takes the move's benefits instead of you. In a fight, a strong hit gives you and your ally initiative. The app doesn't track your ally, so it rolls the move like Secure an Advantage and shows your ally's benefits as a note. Pick it from the full move list (`/moves`). The decision model never suggests it. Your Secure an Advantage abilities apply too, and their adds help your roll. The rulebook gives their benefits on a hit to your ally, though, so the app shows those benefits as a note. Their costs stay with you. Loyalist's first ability adds +1 and gives you +1 momentum on a hit.

## Experience

You earn *experience* mostly by fulfilling vows (rulebook pages 44 and 45). The amount depends on the vow's rank: 1 for troublesome, up to 5 for epic. Some assets give experience in other ways, and the app adds it.

You spend experience on assets, through the Advance move (rulebook page 103):

| What you buy | Cost |
|---|---|
| A new asset | 3 experience |
| An upgrade: one more ability on an asset you own | 2 experience |

Three asset abilities take 1 experience off some purchases: Animal Kin's second ability for an animal companion, Ritualist's third for rituals, and Weaponmaster's second for combat talents. The app works out the discount for you.

The rulebook says to let new assets come from the story. Whether that fits is up to you. The app only checks that you have the experience. `/asset buy` and `/asset upgrade` spend it.

## Moves the app requires next

Some results call for another move right away. The app keeps a list of these *follow-up moves* and asks you to make each one in order. Until you do, you can't make another move. You can still use `/` commands. The app saves the list, so it survives a restart. It also saves a roll card you haven't applied: if you quit with a card open, the app shows the same card, with the same dice, when you come back.

The follow-ups are:

- **Pay the Price:** after most misses (rulebook page 105). You choose how: the most obvious bad outcome (`o`), ask the oracle whether your likelier outcome happens (`a`), or roll on the table (`t`). The app logs the answer. You decide what it means and apply any cost. The log's "Next:" line reminds you to do both.
- **Endure Harm:** when you're hurt (rulebook page 91). The app takes the harm off your health first, then rolls the higher of your health or iron. If your health is already 0, the rest of the harm comes off momentum.
- **Endure Stress:** when you face shock or despair (rulebook page 95). It works like Endure Harm, with spirit and heart.
- **Face Death** and **Face Desolation:** when an Endure Harm or Endure Stress result says "The harm is mortal" or "You are overwhelmed." For both, you roll heart.
- **Companion Endure Harm:** when a companion is hurt (see [Companions](#companions)).
- **Forsake Your Vow:** when you give up a vow.

On an Endure Harm miss with 0 health, the app asks you to mark wounded or maimed, or to roll on the move's table. Endure Stress does the same with shaken or corrupted. If a table result is fatal, the app adds Face Death or Face Desolation to the list.

The rules say to resolve these moves before anything else happens, so the app blocks other moves until you make them. When a result adds one, the log shows "Owed:" and the move, then a "Next:" line that says what the move does and which key makes it.

### When the fiction means harm

Some harm doesn't come from a move result the app can read. Pay the Price may decide your character is hurt, or a foe may strike while you act. The app can't judge the fiction, so you tell it: `/endure harm 2` owes Endure Harm for 2 harm, and `/endure stress 1` owes Endure Stress. In a fight, `/endure harm` with no amount uses the targeted foe's harm. You then roll the move as usual, with its chance to shake off the harm.

## Oracles

In solo play, the *oracle* answers questions about the world (rulebook pages 22, 23, and 107). You use it when you aren't sure what happens next.

Ask the Oracle has four parts:

- **Draw a conclusion:** Decide the answer yourself. You need no command.
- **Ask a yes or no question:** Choose how likely a yes is, then roll. `/ask` does this, with odds from "almost certain" to "small chance." On a match, the answer is extreme or comes with a twist, and the log shows "match."
- **Pick two:** Think of two answers, rate one as likely, and ask whether it's true. Use `/ask likely`.
- **Spark an idea:** Roll on a random table for inspiration. `/oracle` rolls on any oracle table, like `action`.

The oracle gives an answer. You decide what it means in the fiction.

The likelihood is yours to choose, because it depends on the story so far. If you type only a question after `/oracle`, the decision model suggests a likelihood for a yes or no question, or a table for anything else, and you confirm it or pick another. In a test of 56 questions, the model told yes or no questions from table questions every time, and picked a table that fit 30 of 33 times. Its likelihoods were rougher: 14 of 21 matched the expected one, and 19 of 21 were the expected one or the one next to it. So read a suggested likelihood as a starting point. When the scene points to "likely" and the app suggests "50/50," pick "likely."

## Assets

*Assets* are your character's skills, companions, and magic (rulebook pages 21 and 39 to 44). There are four kinds: companions, paths, combat talents, and rituals. Each asset has three abilities. You start with three assets, and you mark more abilities as you gain experience.

### Abilities that apply on a roll

Many abilities add to a move when something is true in the fiction. Archer's third ability, for example, adds +1 when you Resupply by hunting.

The app can't judge the fiction, so it never turns these on by itself. Before you roll, press `a` on the suggestion bar. The app lists the abilities that could apply to this move. You turn on the ones whose condition holds, because only you know whether it does. The bar shows how many apply, like "a abilities (2)." `a` also works before a follow-up move like Endure Harm.

The app then applies what the ability does: an add, a different stat, extra momentum, extra harm, or a change to the result. Some abilities can be used only once per fight, or only once ever. The app tracks those uses.

### Rerolls and late adds

Some abilities let you act after you see the dice:

- **Reroll:** If an ability you turned on allows a reroll, the roll card shows "r reroll." You pick which dice to roll again. You can reroll once, and only before you burn momentum.
- **Late add:** Some abilities, like Wright's second, let you add after you roll, at a cost. The roll card shows "+ add after rolling."

### Asset moves

Some abilities add new moves, like a ritual's. These appear on the full move list (`/moves`), and the model doesn't suggest them. You pick one from the list and roll it like any other move.

### Lasting effects

Some results last beyond one roll, like a talisman you craft or an elixir you brew. The app calls these *lasting effects*. They appear with your abilities when they apply to a move, and you turn them on with `a` in the same way.

Each kind of lasting effect ends by a different rule. Some end after one use. Some end when you roll a 1 on the action die while using them. Some end when health, spirit, or momentum drops below +1. The app ends these for you. Others last until something in the fiction ends them. `/effects` lists them all, and `/effects end` ends one by hand.

### Companions

A *companion* is a helper character, like a hawk or a horse. A companion has a health meter, separate from yours. You name it with `/asset set`, and then `/asset` commands and the Heal form accept that name too.

When a companion is hurt, you make Companion Endure Harm (rulebook page 94). The harm comes off its health first. Any harm left over comes off your momentum. Then you roll the higher of your heart or its health. If your companion is at 0 health and you miss with a 1 on the action die, the companion dies. The app gives you 1 experience for each of its marked abilities and removes it.

The app can't tell when your companion is hurt in the fiction. When it is, use `/asset harm`. You then owe Companion Endure Harm, and the app asks you to make it. Heal, Make Camp, and Sojourn can restore a companion's health, and the app asks whether a Heal is for your companion.

### Abilities the app shows but doesn't apply

`/asset show` lists every ability's full text. A few abilities don't change a roll, so the app doesn't apply them on one:

- Abilities that only help an ally's moves, like Loyalist's second and third. The app tracks only your character.
- Abilities that change the story but have nothing to roll, like Raven's third or Communion's second.
- Abilities that change something once, when you mark them, like Shadow-kin's stat change. The app applies the change at that point.
- A few abilities that you apply yourself with `/adjust`. Fated's second ability is one. The app logs a reminder when it applies.

## When the app can't apply a result

When a result needs something the app doesn't do, the app logs a note. [How-to guides](how-to.md) shows how to fix a mistake with `/adjust`.
