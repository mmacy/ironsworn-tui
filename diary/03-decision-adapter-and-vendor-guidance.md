# 03: The decision adapter and the vendor guidance

Saturday 24 October 2026, 18:51 to 19:12 PDT. Written by Claude Opus 5.5, the lead agent, with a research subagent and a review subagent.

## What step 3 asks for

Build step 3 is the *decision adapter*: code that turns a turn of play into a request for the decision model, sends it through jevtester, and parses the answers into typed values. jevtester is the user's tool for testing decision models: it knows each model's API and sign-in, and it can save requests as test cases and measure accuracy. The step is done when the default tests pass against recorded responses, and a live test marked `-m live` gets an answer from `decision-1@foundry`, which is Microsoft-Decision-1 hosted on Azure Foundry.

## Subprocess or server

The plan said to run `jevtester decide` as a subprocess for each call, and to switch to `jevtester serve`, jevtester's HTTP server, if the subprocess added more than half a second. I measured it with three live calls, comparing the wall time with the `latency_ms` jevtester reported for the model itself:

| Wall time | Model latency | Overhead |
|---|---|---|
| 2,220 ms | 1,483 ms | 737 ms |
| 1,707 ms | 986 ms | 721 ms |
| 1,570 ms | 817 ms | 753 ms |

`jevtester --version` alone took 0.35 seconds, so about half the overhead is Python starting and importing, and the rest is the `decide` command's own setup. That's over the limit, so the app starts one `jevtester serve` on a free port and posts each request to `/api/decide`. Through the server, the second call on the same message took 455 ms against 442 ms of model latency, an overhead of 13 ms. The server took 0.77 seconds to start the first time and 0.46 seconds the second.

Two details of the server launcher came from thinking about failure. The first draft piped the server's output into the app, but uvicorn, the web server inside jevtester, logs a line per request, and a pipe that nobody reads fills up after a few tens of kilobytes and blocks the writer. The server now logs to `.jevtester/serve.log`, which git already ignores. And after the first recording run, `ps` showed three `jevtester serve` processes still running, which looked like orphans from my launcher. They had started 2 hours and 34 minutes earlier, from another checkout, `~/repos/jevtester-backend`, in a different session. Mine had shut down cleanly.

## Recording fixtures

The default tests never call a hosted model, so they run against jevtester's JSON output recorded into `tests/fixtures/`. I recorded two responses: one real answer from `decision-1@foundry`, and one failure. For the failure I sent the request to `clef-flash@ollama`, a local model the user hasn't downloaded. I expected jevtester to answer `not_ready` without sending anything, as its API document says for a target that isn't ready. It sent the request instead and got `bad_request: ... 404 model 'clef-flash' not found` back from the local Ollama server, because jevtester hadn't run a health check on that target since the server started. I renamed the fixture `decide-target-failed.json` to match what it records. Ollama doesn't download a model on a 404, so nothing was downloaded. I checked both fixtures for tokens and keys before committing them: the `raw` field holds only the model's answer body.

## The user's nudge toward the vendor docs

While I was writing the adapter, the user wrote: "ensure you read all the latest guidance for decision models so we're using them to best effect. Cloudflare and TypeSafe have solid docs." I hadn't read them. I sent a research subagent to collect the guidance and critique my draft request, and kept building the parts that didn't depend on wording. It ran for about 6 minutes with 33 tool calls and saved copies of every source in the session's scratchpad. Before acting on its report, I checked its key quotes against those copies with `grep`.

TypeSafe turned out to be the maker of Jev, which it calls "the first System One model". It defined the `/v1/systemone` API that both Decision-1 and Cloudflare's Clef follow. Cloudflare's launch post says Clef is "in the same family as Typesafe's Jev". TypeSafe's docs are the detailed guide; Cloudflare publishes reference pages and open-weights code but no guide to writing questions.

The findings that changed my draft:

- **The model reads field names, and coded values hurt.** My state had `"context": "exploring"` and `"initiative": null`. TypeSafe warns that "the model can read an empty list as a signal", and its notes on Jev say it "will perform better on semantic representations than numeric". The state now has a `circumstances` sentence that code writes, such as "Kira is in a fight, and the foe has initiative."
- **Questions should name the fields they judge.** The `move` question became "Which move does the action in `player_says` trigger, given `circumstances` and `situation`?" A test checks that every question names at least one field and only fields the state has.
- **No presuppositions.** My stat question asked "Which approach does the character take for Face Danger?", which assumes the move before the model has picked it. Code reads only the stat answer for the move the player confirms, so the question doesn't need the move's name. It now asks "How does the character go about the action in `player_says`?"
- **Describe situations, not negations.** `no_move` said "Nothing risky or uncertain happens", and `cannot_tell` said "The player's words don't show what the character does". Both now describe what you'd see: "The character does something safe or routine, such as talking, eating, or walking a quiet road" and "The player asks a question, describes the scene or a feeling, or speaks out of character". Every move criterion is now a situation with "The character" as its subject, and Face Danger and Secure an Advantage name the line between them: doing the risky thing now, against preparing before it.

Some findings need measurement, not edits, so they went into step 4's list. The vendors disagree on abstaining: Microsoft recommends a `cannot tell` option, while TypeSafe says "As of Jev 1.14, this companion Noul usually works better than a 'none of the above' option". A *Noul* is a yes/no question with a probability. Clef's reference code also decides all questions in a request jointly and sorts the options by name, so on Clef the stat questions might move the `move` answer, and option order can't be controlled. These are recorded in a new page, `docs/decision-model-guidance.md`, with the sources and what the project does with each finding.

One suggestion didn't fit the tools. TypeSafe suggests describing options the model confuses with objects, with fields like `what`, `not_for`, and `examples`. jevtester's choice criteria are typed `dict[str, str]`, so it can't send them. The user then wrote "Modify jevtester if it makes sense." I decided to wait for step 4's numbers: the change is worth making only if one-line criteria can't separate the moves the model confuses.

## One message, before and after

I re-recorded the fixture with the new request. On the same message, "I creep along the ditch to get behind the ridge where they can't see me", Decision-1 picked Secure an Advantage both times. With the old wording its confidence was 0.56 and 0.53 on two calls; with the new wording it was 0.98 on two calls, with Face Danger second at 0.012. That's one message, so it shows the wording matters, not how much. Step 4's 120 phrasings will measure it.

## Targets

The user also wrote: "Use the Decision-1 model on Foundry. Ollama models aren't downloaded and won't be until I get back to civilization (not working on the hotspot)." Live calls and the step 4 runs use `decision-1@foundry`. The plan's step 4 compares two targets, so I'll ask before adding the hosted `clef-flash@workers-ai` as the second.

## The review

A review subagent read the branch against jevtester's own code, without running anything that calls a hosted model. It ran for about 4 minutes with 22 tool calls. Its findings, and what I did with each:

- **A shutdown that could orphan jevtester.** The app starts the server through `uv run`, which starts jevtester as its own child. The reviewer tested signals with a stand-in: uv 0.8.22 forwards SIGTERM to its child, but SIGKILL kills only uv, and the child keeps running. My launcher sent SIGKILL when the server hadn't stopped within 5 seconds, which can happen: uvicorn waits for open requests before it shuts down, and jevtester lets a request to the model run for more than 60 seconds. The server now runs in its own process group, and shutdown signals the whole group. A new test starts a stand-in server that has a child process of its own, and checks that the child is gone after shutdown.
- **Two timeouts of the same length.** The client waited 60 seconds for a reply, and jevtester waited 60 seconds plus a grace period for the model. A slow model would therefore make the client give up first, with a misleading "isn't reachable" error, instead of receiving jevtester's own timeout result. The request now asks jevtester for a 30-second timeout, and the client waits 45.
- **Answers that parse but can't be used.** jevtester can return `ok: true` with the `move` answer missing, or with a choice the question doesn't have, each flagged only by a warning. My parser accepted both, and the second would have crashed later on a lookup. A `Decision` is now `ok` only when it has a `move` answer that names one of the question's options, and it keeps jevtester's warnings. The parser also accepted only choice answers, which would have failed the whole response on the companion yes/no question that step 4 plans to test.
- **Criteria that overlapped.** My new `no_move` description, "talking, eating, or walking a quiet road", collided with Compel and Gather Information (talking), Make Camp (eating), and Undertake a Journey (walking a road). It now reads "The character does something with no risk and no doubt about the outcome, such as small talk with a friend over a meal in a safe place". Make Camp and Sojourn both said "rests", and now name the line between them: away from any settlement, against in a community. Face Danger, Secure an Advantage, and Gather Information now differ by purpose.
- **A presupposition I missed.** I had removed the move name from the stat questions but kept "How does the character attack in `player_says`?" for the attack question, which goes out with every fight request, including "I ask the raider to yield". My test only checked for the words "Face Danger" in the exploring context, where there's no attack question, so it passed for the wrong reason. The attack question now uses the same wording as the others, and the test checks every question in every context against every move name.
- Smaller fixes: every error now reaches the caller as a `DecideError`; startup tries a new port if another process takes the free port first, and checks that the server answering is jevtester; requests bypass any HTTP proxy; and two stale sections of the plan now describe the server.

Re-recording the fixture after these changes gave a confidence of 0.934 and 0.92 for Secure an Advantage on the ditch message, down from 0.98 with the wording before the review. One message can't say whether the new criteria are better or worse; step 4 will measure that.

All four gates pass with 321 tests, and the live test passes against `decision-1@foundry`.

## Next

Build step 4, the recognizer experiment: a `suggest` command, 120 hand-written phrasings with expected moves, the question sets and policy, and `jevtester report` numbers. Then I stop for the user's review.
