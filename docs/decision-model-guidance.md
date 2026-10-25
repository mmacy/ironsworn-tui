# Decision model guidance

This page records the vendor guidance on writing requests for decision models, and what this project does with it. The quotes below were checked against copies of the sources downloaded on 2026-10-24.

## Sources

- TypeSafe makes Jev, the first System One model, and defined the `/v1/systemone` API that Decision-1 and Clef follow. Its docs are the most detailed guidance on writing requests: [docs.typesafe.ai](https://docs.typesafe.ai/llms.txt) (append `.md` to a page URL for Markdown), and its [agent skill](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md).
- Microsoft: [Deploy and use Microsoft-Decision-1 in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-microsoft-decision).
- Cloudflare: the [Clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/) and [Clef](https://developers.cloudflare.com/workers-ai/models/clef/) model pages, the [launch changelog](https://developers.cloudflare.com/changelog/post/2026-10-01-clef-workers-ai/), the [launch post](https://blog.cloudflare.com/clef-decision-models/), and the open-weights [reference code](https://huggingface.co/Cloudflare/clef-flash). Cloudflare has reference docs but no guide to writing questions.

## What the guidance says

- **State.** Use a JSON object with descriptive keys, because the model reads them. Include only what the questions need: "A field added for one question can sway the answer to another, and the model can read an empty list as a signal" (TypeSafe). Use words, not codes.
- **Questions.** Write one judgment per question, name the state fields it judges with backticks (TypeSafe: "name it in the `instructions` with a dot-and-index path to its key"), and avoid presuppositions. A question about a move that may not have been chosen needs no "if" clause, because code reads only the answer it needs.
- **Options.** The model sees option names and descriptions. Describe each option as a concrete situation, keep options distinct, and name the case that causes confusion. TypeSafe suggests objects with fields like `what`, `not_for`, and `examples` for options the model confuses.
- **Abstaining.** The vendors disagree. Microsoft: "Include an abstention option, such as `cannot tell`, when the model shouldn't make a forced choice." TypeSafe: "As of Jev 1.14, this companion Noul usually works better than a 'none of the above' option."
- **Option order.** Jev 1.13 "leans toward the option that comes first", and Microsoft says Decision-1's scores "can change based on how you phrase or order questions and options". Clef's reference code sorts options by name before encoding them.
- **Many questions.** Send questions that share a state in one request. On Jev, "Every answer is independent." Clef's reference code says "Decide every field jointly" and sends the question id to the model, so on Clef the stat questions may shift the `move` answer.
- **Confidence.** Confidence measures how concentrated the probabilities are, not whether the answer is right. With many options, TypeSafe suggests the top-to-second ratio, `p_max / p_second`, alongside a floor on the top probability. Thresholds don't carry over from one model to another.
- **Limits.** Clef on Workers AI takes 2 to 255 options and up to 64 questions, and truncates a long state silently. Microsoft documents no limits for Decision-1.

## What this project does

The requests apply it:

- The state has `character`, `circumstances`, `situation`, and `player_says`. `circumstances` is a sentence such as "Blarg is in a fight, and the foe has initiative", in place of a `context` id and a null `initiative`.
- The `move` question asks "Which move does the action in `player_says` trigger, given `circumstances` and `situation`?" Every stat question, including the one for an attack, asks "How does the character go about the action in `player_says`?", with no move name.
- Each guide criterion is a concrete situation. Criteria for moves that overlap name the line between them: Face Danger overcomes a danger directly, while Secure an Advantage sets up an edge for an action still to come, and Gather Information learns facts. Make Camp is away from any settlement, and Sojourn is in a community.
- `no_move` and `cannot_tell` describe situations instead of negations, and they come last in every list.

The move recognizer experiment measured, on Decision-1 and Clef-flash ([results](https://github.com/mmacy/ironsworn-tui/blob/main/experiments/results.md)):

- The guide criteria beat the Datasworn trigger text on both targets, so play uses them.
- A `cannot_tell` option on the stat questions won most stat misses, so the stat questions have none.
- The companion `acts` question lowered move accuracy on both targets, because it answered no for many real actions. The `move` question has a `cannot_tell` option instead.
- Messages that name a move ("Roll Face Danger! I pour myself another cup of tea") didn't pull either model toward the named move.
- Whether the stat questions change the `move` answer is unsettled. Removing the stat `cannot_tell` option changed one `move` choice on Clef-flash and none on Decision-1, but probabilities moved by up to 0.09 on both, and one run of each can't separate that from run-to-run variation.

The oracle request applies the same guidance:

- The state has `character`, `situation`, and `question`, the text the player typed after `/oracle`.
- It asks three questions, each one judgment: `kind` ("What kind of answer does `question` ask for?"), `likelihood` ("How likely is a yes to `question`, given `character` and `situation`?"), and `table` ("Which oracle table gives the answer that `question` asks for?"). Code reads `likelihood` or `table`, as `kind` says, so neither needs an "if" clause.
- `kind` has a `cannot_tell` option, for text that isn't a question about the story. `likelihood` and `table` have none.
- Each option is a concrete situation: a likelihood is how the situation leans ("A yes fits the situation better than a no"), and a table is what it gives, with an example ("What a person wants, such as to obtain an object or to avenge a wrong").
- The `table` question has 22 options, the tables the player rolls. That's under the 26-option limit of the Ollama target, so the request doesn't need a category question first.

The oracle experiment measured, on Decision-1:

- A `cannot_tell` option on the `table` question won 7 of the 33 questions a table fits, and those were all the table misses, as the stat questions' `cannot_tell` option did. Without it, the same 33 questions got a fitting table 30 times instead of 26.
- The `kind` answer was right for all 56 questions in both runs, at a confidence of 0.51 or more.
- The likelihood's exact answer was right 14 of 21 times. The model rarely followed the wording: "I doubt they left anything, but is there food in the cart?" got `likely`. Play shows the likelihood as a suggestion the player confirms.

Still to test: option order with `jevtester probe`, whether the `character` field sways the stat answers, and acting on the top-to-second ratio as well as confidence.

jevtester's choice criteria are strings, so the structured criteria TypeSafe suggests would need a jevtester change. The user allowed changing jevtester if it makes sense. The moves the models still confuse (a shield bash read as an attack, a rallying shout read as Compel) are few and borderline, so they don't justify that change yet.
