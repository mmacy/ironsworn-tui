# Decision model guidance

This page records the vendor guidance on writing requests for decision models, and what this project does with it. A subagent gathered it on 2026-10-24, and the quotes below were checked against downloaded copies of the sources.

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

Build step 3 applied:

- The state has `character`, `circumstances`, `situation`, and `player_says`. `circumstances` is a sentence such as "Kira is in a fight, and the foe has initiative", in place of a `context` id and a null `initiative`.
- The `move` question asks "Which move does the action in `player_says` trigger, given `circumstances` and `situation`?" Every stat question, including the one for an attack, asks "How does the character go about the action in `player_says`?", with no move name.
- Each guide criterion is a concrete situation. Criteria for moves that overlap name the line between them: Face Danger overcomes a danger directly, while Secure an Advantage sets up an edge for an action still to come, and Gather Information learns facts. Make Camp is away from any settlement, and Sojourn is in a community.
- `no_move` and `cannot_tell` describe situations instead of negations, and they come last in every list.

Build step 4 tests:

- The two criteria styles, as the plan says.
- A companion Noul ("Does `player_says` describe something the character does?") against the `cannot_tell` option.
- Whether the stat questions change the `move` answer on Clef.
- Option order, with `jevtester probe`.
- Whether the `character` field sways the stat answers.
- A phrasing that tries to dictate the move.
- Acting on the top-to-second ratio as well as confidence.

jevtester's choice criteria are strings, so the structured criteria TypeSafe suggests would need a jevtester change. The user allowed changing jevtester if it makes sense. Make that change if step 4 shows the model confusing moves that one-line criteria can't separate.
