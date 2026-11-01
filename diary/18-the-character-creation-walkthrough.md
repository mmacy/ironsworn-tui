# 18: The character creation walkthrough

Saturday 31 October 2026, 17:51 to 19:03 PDT, plus a short survey of the code before the branch was cut at 17:51, and Sunday 1 November 2026, 06:00 to 06:15 PST, for the play screen's wording. Written by Claude Opus 5.5, the lead agent, working alone.

## The request and the three decisions

The user wrote: "I think we need a character creation walkthrough experience."

Until now, `ironsworn-tui new` took every choice as a flag: `--stats edge=2,heart=2,...`, `--assets archer,hawk:2,wright`, `--vow`, and `--bond`. A newcomer had to read the tutorial to build that command, and had to run `new --assets help` to learn the asset ids.

I read the rulebook's campaign setup summary on printed page 202. It has eight steps: create your character, create your world, mark background bonds, write a background vow, envision an inciting incident, set the scene, swear an iron vow, and take your next steps. The flag form covered steps 1, 3, and 4. The vendored Datasworn data already had `truths.yaml` and `atlas.yaml`, but no code read them.

I asked the user three questions, and they answered:

- Where the walkthrough starts: "Bare `new` opens it". `ironsworn-tui new` with no options opens the walkthrough, saves the campaign, and starts play. The flag form stays.
- How much of the setup it covers: "Full setup into play". That means world truths, the inciting incident, and the first Swear an Iron Vow, not only the character.
- How much rules text each step shows: "A short rules line per step".

## The data: truths, regions, and a bad roll range

`Datasworn` gained two indexes. `truths` holds the 11 world truths, each with three options. Each option has a roll range on 1 to 100, a description, and a *quest starter*, a story idea that follows from the truth. `regions` holds the nine regions of the Ironlands from the atlas, each with a summary and a quest starter.

The loader checks that each truth's three options cover 1 to 100 exactly once. That check failed on the first run: the second Mysticism option ("Magic is rare and dangerous, but those few who wield the power are truly gifted") had the range 68 to 100, the same as the third option. No roll could pick it. The rulebook page shows dice icons, not numbers, but the other ten truths all split at 33 and 67. I changed the range to 34 to 67 in the vendored YAML, and `ironsworn_tui/data/README.md` now records that one change.

Asset text fields now keep their Datasworn labels, so the walkthrough can ask for a Devotant's "god's name" instead of `gods_name`.

## The campaign model and a rules fix

`Campaign` gained a `World`: the chosen truths, the region, the place, and the inciting incident. No rule reads it, and a new `/world` command lists it. `SCHEMA_VERSION` went from 4 to 5, with no migration, as the project's rules say.

The rulebook says a background vow is extreme or epic (page 195). The flag form accepted any rank for `--rank`. `new_campaign` now refuses a rank below extreme.

## Setup without a screen

`creation.py` holds the logic with no UI code. `Setup` is the walkthrough's answers. `begin_campaign` builds the campaign from them through the existing `create_character` and `new_campaign`, so the walkthrough and the flag form share every check. It also logs the inciting incident and the scene. `open_play` makes the first move: in media res, it makes Swear an Iron Vow, so the roll card is saved in the campaign file before the play screen appears. After a prologue, it logs a note that says to swear the vow with `/vow swear` when the problem arrives. The module also rolls the oracles the walkthrough offers: an Ironlander name, a settlement name from the quick name tables, and an action and a theme.

## The walkthrough app

`walkthrough.py` is a second Textual app. It has 22 steps: name, stats, assets, asset details, equipment, the 11 truths, where the story begins, bonds, background vow, inciting incident, the opening scene, and a review. The heading shows the rulebook step and "Step n of 7", and each step has a rules line. Enter moves to the next field, and from a step's last field to the next step. Esc goes back and keeps the answers. Ctrl+Q quits and saves nothing.

I wrote three small widgets. `ChoiceList` picks one option with the arrows or digits. `StatGrid` arranges the bonuses 3, 2, 2, 1, 1 across the stats. A bonus that's used up is taken from the stat that had it. `AssetList` is an option list of the 78 assets by type, and Space picks or drops one while the right side shows its abilities. The asset details step appears only when a picked asset needs something: a starting ability for a companion, a name, or a choice such as Ironclad's armor. Shadow-Kin's and Battle-Scarred's first abilities change stats, so the list shows them dimmed and won't select them.

## What the screenshots caught

I drove the app headlessly, saved SVG screenshots, and converted them with `rsvg-convert` to look at each step. That found five problems:

- The asset list lost its `[x]` marks, because Textual reads `[x]` as markup. The prompts became `Text` objects.
- The review step ignored Enter, because it has no control to take it. The app now binds Enter as a fallback, and a focused control's own Enter still comes first.
- Focusing the background vow's input scrolled its label out of view. Focus now happens without scrolling.
- Rich's grid padding didn't put blank lines between long truth options, so `ChoiceList` adds empty rows.
- Asset abilities showed two numbers each, the key and the ability number. The list now uses the key as the ability number.

The headless driver also showed that the walkthrough returned nothing after the review. That was the missing Enter binding.

## Opening play

The cli tests replace both apps' `run` methods. One test checks that a bare `new --no-model` saves the campaign, prints its path, and opens play on the Swear an Iron Vow card. I also ran the real command in a pseudo-terminal. It drew "Create your character", quit on Ctrl+Q, printed `Nothing saved.`, and exited with 1.

The opening screen showed one problem. The play screen's welcome note ("Welcome. Type what Blarg does...") appeared only when the log was empty, and a walkthrough campaign's log already holds the bond, the inciting incident, and the scene. I changed the condition to "no message typed yet". The screenshot of the in media res opening then showed the welcome between the roll and its outcome, telling the player to type while a roll card waited. The welcome now appears once no card waits.

## Tests and timings

The new pilot tests took 77 seconds at first, because each key press waits for the screen to update, about 80 ms each, and the helpers typed every character. The helpers now set an input's value and press only Enter, and one test still types for real. The file then took about 37 seconds for 20 tests, close to the app tests' pace.

Two existing tests changed. `/or` now completes to `oracle` or `world`, because completion matches anywhere in a name, so that test types `/ora`. Asset text field labels are now a mapping.

All five gates passed: ruff format, ruff check, pyright with 0 errors, 1,174 tests, and the docs site build with "No issues found". The branch changes 40 files, with 4,551 lines added and 1,172 removed, most of them in the redrawn SVG screenshots.

## The docs

The tutorial now creates Blarg in the walkthrough: wits 3, Archer, Wayfinder, and a hawk named Kestrel. The truths are left to the dice. Blarg begins in Ravenford in the Havens, with a bond to their brother Torvin. The inciting incident is "Raiders took Torvin, and they'll sell him at the coast before the thaw", and in media res Blarg swears "Free my brother from the raiders". The screenshot script builds the same campaign through `begin_campaign` and `open_play`, so every play screenshot now shows Kestrel and the setup lines. It also draws three new walkthrough screens. The reference documents both forms of `new`, the walkthrough's steps and keys, exit status 1, and `/world`. `playing.md` gained a section on the eight setup steps with their rulebook pages.

## The user's review of the wording

After the PR opened at 18:28, the user asked "What's \"media res?\"". My summary had shortened "in media res", Latin for "in the middle of things", to "media res".

Then they asked: "When have you ever seen hint text in a text box that starts with \"Such as\"?" Every placeholder read like "Such as Blarg", and two read "Optional: ...". The user added: "And \"the Destructor\" probably isn't a good example, is it? There's probably a better one from the rulebook, eh?" The placeholders are now bare example values from the rulebook's example character, Saskia (pages 193 to 199): "Saskia", "a former raider turned farmer", "Cinderhome", "Defeat the Red Moon clan", and "A mysterious sickness has struck the overseer". Optional fields say so in their labels. The play screen's move details form had the same habit ("A name and a rank, such as Wolf dangerous"), and the user agreed to fix it there too.

Next: "Is it really \"give\" your stats in the rulebook?" It isn't. Page 33 says "arrange these bonuses across your five stats", and page 47 says "Set your stats". The user said: "Do that across everything, not just \"give\" and the stats." I reread the rulebook pages behind each step and reworded the walkthrough, the setup docs, and the asset errors to its terms:

- Assets have a *default ability* and a *starting ability* (pages 21 and 42), not an ability that "starts marked". The errors now read "Hawk doesn't have a starting ability; choose one from 1 to 3" and "Archer already has a default ability".
- Harm comes from being "armed with a deadly weapon" or "unarmed or using an improvised or simple weapon" (page 19).
- A truth is chosen and made "true for your version of the Ironlands" (page 122), and the rulebook says to "fill in the blanks" as you play, so "Leave it open" became "Leave it blank, and fill it in as you play".
- The two ways to start are "the normal world" and "in media res" (page 198), and the inciting incident is "an imminent threat or compelling need" with "a ticking clock" (pages 196 to 197).

One finding from that reread: the rulebook doesn't offer a roll for the truths. Page 122 says only to choose an option or "make your own truth". The roll ranges come from Datasworn. The walkthrough keeps the roll and has no way to write your own truth.

The next morning the user asked for the same check on the rest of the play screen and its `/` commands. I listed every string literal in the app's modules with a short script over the Python syntax tree, about 900 lines, and checked the ones a player sees against the move text in Datasworn, which is the rulebook's text, and against rulebook pages 14, 35, 36, 39, 42, and 44. The roll card's option labels, such as "Bolster your position" and "Make good use of your resources", already matched the rulebook. About 40 strings didn't:

- `/ask` took a `<likelihood>`. The rulebook says "Decide the odds of a 'yes'", so it's now `<odds>`, and the help says to "pick two" options, as Ask the Oracle does.
- The suffer prompts said "Blarg loses 2 health, then rolls to shake it off". The moves say "suffer -health" and "roll +health or +iron, whichever is higher", and "Shake it off" is only one of the strong hit's choices. Face Desolation's prompt said "the brink of despair", and the move says "the brink of desolation".
- `/endure stress` was "Owe Endure Stress when your character is shaken". Shaken is a debility, so that summary named the wrong thing. The summaries now use the moves' triggers: "when you face physical damage" and "when you face mental shock or despair".
- Turn the Tide was "armed" and "disarmed". The walkthrough now says "armed with a deadly weapon", so the two meanings collided. The move says you "steal initiative from your foe", and the log now says "Turn the Tide is ready: your next move steals initiative".
- Asset abilities were "marked". The rulebook fills in an ability's dot and calls buying another one an *upgrade* (page 42), so the messages say "filled in" and "upgraded". The `/asset` help now lists the four asset types, companions, paths, combat talents, and rituals, where it had "special talents, companions, and paths".
- The Out of Supply and Face a Setback notes said "exchange 2 momentum for health, spirit, supply", which reads as a gain. The moves exchange each "-momentum for any combination of -health, -spirit, or -supply", and the notes now keep the minus signs.
- The log's next step said "Next: imagine what you learn". The rulebook's verb is *envision*.

Seven tests quoted the old strings, and ten screenshots showed the old "Next:" line, so I updated the tests and redrew the screenshots. The internal names, such as the decision model's `likelihood` question, keep their names, because no player sees them.

## What's next

The user hasn't played through the walkthrough yet. World truths are stored and listed but never shown to the decision model. Whether the scene or the truths should reach the model's state is a question for `decision-model-guidance.md` before anyone changes the requests.
