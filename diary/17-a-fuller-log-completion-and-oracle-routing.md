# 17: A fuller log, completion, and oracle routing

Sunday 25 October 2026, 10:16 to 11:30 PDT. Written by Claude Opus 5.5, a subagent of the lead agent, from the merged PRs, the user's messages, and the oracle work in PR #30.

## What the user ran into

The user played Blarg's first session and got stuck. At 10:16 they wrote three requests in one message:

> slash commands need to provide the available options in greyed-out text on the command line, like "/oracle [table1 | table2 | tableblah]" where the square brackets and everything in between is what's available for the command. I should be able to type letter(s), it filters the options per letter(s) in the names of the options available, and I can either hit TAB to to complete the currently selected option or arrow to another one and hit TAB to complete it; this is the same funcitonality as pretty much every CLI ever.

> The results of what I picked for the move and what the move was needs to be added to the log in the right pane. I said "I look around to gain an idea of my surroundings" and all that info about what Gather Information was goes away and all I got was the "Gather Inforamtion +wits: 6 + 3 + 0 = 9 vs 3, 4 strong hit" line, so I'm not sure what to do next. There was a hint in the previous message that appeared above the chat box that said "Ask the Oracle if you're not sure." and so then I tried to do that, but since I have no idea what "table" is/are available I am kinda stuck. That's where the previous feature request comes from.

> Every slash command should have a 'help' option that provides information to the new player. There will be many like me that don't know Ironsworn and are not going to read the docs for this project nor the Ironsworn rules and they're going to try to bash their way through this to learn it. We need to make that experience pleasant and workable.

At 10:26 they added: "There needs to be some way to add notes to track the questions I ask, sorta like /scene (I guess?). So if I ask something like, "Do I know which castle I'm in?" and then do '/ask almost certain', I have a record of what I "asked.""

## PR #27: the log explains each move's result

Merged at 10:34. The log now keeps the whole turn, so a player who doesn't know the rules can see what happened and what to do next. After a move it shows what the move is for (the first time the campaign makes it), the roll, the result's text, each option picked on the card, each change with its new value (`Momentum +2 (now 4)`), and a `Next:` line when the result asks for something the app doesn't do. Gather Information's strong hit now ends with "Next: imagine what you learn and type it, or ask the oracle (/ask likely for yes or no, /oracle action for ideas)."

The engine works out the changes by comparing a snapshot of the campaign before and after the move, so a new effect kind is logged without its own log code. Each log kind has its own color. The campaign saves which moves it has explained, so `SCHEMA_VERSION` went to 4. One bug was fixed: `plain_text` left Datasworn's `{{table>...}}` markers in the Endure Harm, Endure Stress, and Pay the Price text. The PR added 1,533 lines and removed 705, and 981 tests passed.

## PR #28: completion, help, questions, and notes

Merged at 10:43. A command registry, `registry.py`, describes every command's arguments, options, summary, and help, and parsing, completion, `/help`, and usage errors all read it. After a `/`, the input line shows the options as dim ghost text, such as `[action | theme | +22 more]`. Typing filters them, Up and Down select, and Tab completes. Every command takes `help`. The oracle tables got short grouped names such as `ironlander-name`, which fixed `/oracle descriptor` matching two tables. `/ask` and `/oracle` take a question after the likelihood or table, and the log keeps it with the answer. `/note <text>` writes a note to the log. The PR added 2,608 lines and removed 713, and 1,038 tests passed.

## The oracle question

At 10:27 the user asked: "Could we use a decision model call to identify the Oracle table from an oracle question?" At 10:29: "Make it so." The lead agent's brief asked for one decision request per question, an accuracy test on `decision-1@foundry` before wiring it into play, and the same confirm-first flow as move suggestions.

### How many tables

Datasworn has 38 oracle tables. Two are the suffer tables and five are the Ask the Oracle odds, which moves and `/ask` roll. Pay the Price is a move's table too. Of the other 30, Ironlander names A and B roll as one name, and the seven settlement-name tables are rolled by `settlement-name`. That leaves 22 tables a player asks for. The Ollama target takes at most 26 options per question, and 22 fit, so the request needs no category question first. `oracles.ASKED_TABLES` holds the 22, and `/oracle pay-the-price` still works by name.

### The request

One request, three questions, each one judgment, as the decision model guidance says:

- `kind`: "What kind of answer does `question` ask for?" with `yes_no`, `table`, and `cannot_tell`.
- `likelihood`: "How likely is a yes to `question`, given `character` and `situation`?" with the five odds, each a situation such as "A yes fits the situation better than a no".
- `table`: "Which oracle table gives the answer that `question` asks for?" with the 22 tables, each described by what it gives, such as "What a person wants, such as to obtain an object or to avenge a wrong".

The state is the character, the scene line, and the question. Code reads `likelihood` or `table`, as `kind` says.

### The accuracy test

`experiments/oracle-phrasings.yaml` has 56 hand-written questions: 21 yes or no questions with at least four per likelihood, 33 table questions covering every table, and two that aren't about the story ("How does burning momentum work again?"). Ambiguous ones list the other answers that count. "Are the riders friend or foe?" accepts either kind, and "How many raiders are in the camp?" has no fitting table. `write-suites` turns them into `recognizer-oracle`.

The first run had a `cannot_tell` option on the `table` question. Results on 56 requests:

- `kind`: 56 of 56.
- Likelihood: 19 of 21 acceptable, 14 of 21 exact.
- Table: 26 of the 33 questions a table fits.

Every table miss was `cannot_tell`. "What's the child's name?" got `cannot_tell` at 0.75 and `ironlander-name` at 0.24. This is the same failure as the stat questions' `cannot_tell` option in entry 5.

The second run dropped that option, and was the last allowed. On the same 56 questions:

- `kind`: 56 of 56, with confidence 0.63 or more.
- Likelihood: 19 of 21 acceptable, 14 of 21 exact. ECE 0.315.
- Table: 30 of 33 (90.9%). ECE 0.103.
- p50 latency: 386 ms.

The three table misses were "Who is the rider?" (`ironlander-name` at 0.85, expected `role`), "What did the elder do before she led the village?" (`action` at 0.65, expected `role`), and the friend-or-foe question's table (`plot-twist`, unused because its kind was `yes_no`). Without the option, "How many raiders are in the camp?" got `challenge-rank` at 0.69: the model doesn't abstain when no table fits.

The likelihood is close but rarely extreme. Of 7 inexact likelihoods, 6 were one step off, and 3 of the 4 `small_chance` questions got `unlikely`. The two misses were at 0.30 and 0.31. One was the wording cue "I doubt they left anything, but is there food in the cart?", which got `likely`.

jevtester has no price for Foundry, so the 112 requests have no recorded cost.

### Thresholds

`suites/policies/oracle.yaml` preselects the first option when the `kind` confidence is at least `act` (0.5) and the chosen likelihood's or table's probability is at least `pick` (0.4). On run 2, that preselects an acceptable answer for 48 of 56 questions and a wrong one for 3. It preselects nothing for 3 yes or no questions, which include both wrong likelihoods, and for the two that aren't about the story. No `pick` up to 0.6 removes a wrong table, because they had 0.65 or more. jevtester's policy accuracy is 0.804, because it scores only each case's main answer.

### In play

`/oracle Do I know which castle I'm in?` turns the bar to oracle mode: `Oracle:` and the question, then every option with its key. The kind the model chose comes first, each group most probable first, so `1 Ask unlikely 0.88` is selected, then the other likelihoods, then the 22 tables. Enter rolls it, and the log reads `Ask (unlikely): Do I know which castle I'm in? 80: yes`, as if the player had typed `/ask unlikely`. Any other key picks another option. When the model can't tell, or the request fails, the bar lists every table, then every likelihood, with nothing selected. `/oracle` alone shows that list without a request. After the roll or Escape, the bar returns to a move suggestion it interrupted.

Parsing needed one change: `Arg.skip`, an argument that passes text that isn't one of its options to the next argument. `/oracle location Where does the trail lead?` still rolls `location`. Each answered question becomes a case in `suites/play-oracle.yaml`, tagged `corrected` when the player rolled something else.

### Bugs fixed on the way

- `test_repository_settings_file_loads` failed in any checkout with a `jevtester.local.toml`, which the main checkout has. It now expects whichever config `load_settings` picks.
- `test_play_cases_can_be_run_and_reported`, a live test, copied the placeholder `jevtester.toml` and assumed the play suites were empty. It now copies the config the app uses and starts from empty play suites.
- The suggestion bar wrapped its options at any space, so a key could end one row and its name start the next. The bar now lays out whole labels per row, for moves and oracles.

While this PR was open, PR #29 merged the fixes from a newcomer playtest. One of them made a missing argument list its options, and its test used `/oracle` alone, which now opens the full list instead of failing. The test uses `/asset buy` now. The bar's new row layout also needed a fallback width for a test that renders the bar without a running app.

All five gates pass with 1,104 tests.
