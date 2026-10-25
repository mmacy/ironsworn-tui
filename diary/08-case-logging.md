# 08: Case logging

Saturday 24 October 2026, 21:06 to 21:32 PDT. Written by Claude Opus 5.5, the lead agent, with one review subagent.

## The request and two decisions

After step 6 the user asked to hear more about the last two build steps. Step 7 turns play into test data: every message the decision model answered becomes a jevtester case, labeled with what the player actually did. I raised two concerns about the plan's version.

The first was that every message the user types would be committed to git, because the play suites live in the repository's `suites/` folder. The user decided: "No need to gitignore the suites - repo is private with no plans to go public."

The second was the plan's rule that pressing Escape without rolling labels the message `no_move`. Escape also means "not now" or "let me rethink", so that rule would put wrong labels into the accuracy data. I proposed an explicit key for "no move here", with Escape saving nothing. The user agreed: "yeah, explicit no move sounds good."

## How a case is saved

The plan said to run `jevtester case add` for each turn, but a subprocess costs about 0.7 seconds, measured in step 3, and the app already keeps a `jevtester serve` running. The server's API has the same operation, `POST /api/suites/{name}/cases`, so the client got an `add_case` method.

Reading jevtester's `add_case` showed two constraints. It rewrites the whole suite file, and it refuses a case whose id the suite already has. So `write-suites` creates the three play suites once and never touches them again, and each case id combines the character's name and the time to the microsecond, such as `kira-20261024T213005123456`.

The engine remembers which decision the player's next move answers. `accept` stores it, along with the context at the time of the message, because a move like Enter the Fray changes the context: a fight started from the `exploring` context must be saved to `play-exploring`, where the question asked offered Enter the Fray. The case is saved when the move passes every check and before anything changes, so a refused move saves nothing and a retry saves once. The case's state is the exact state the model saw, taken from the decide response, and the case gets a `corrected` tag when the player's move differs from the model's top answer. A failed request has no decision, so nothing is saved. If saving fails, a note goes into the log and play continues.

## Verifying it

A scripted test plays four messages and checks where each case lands: Face Danger as suggested, Enter the Fray when the model said Secure an Advantage (tagged `corrected`, and saved to `play-exploring` even though the move starts a fight), `n` in the fight (saved as `no_move` to `play-fight`), and Escape (not saved).

The plan's done criterion is that `jevtester run` and `jevtester report` work on the saved cases, which needs the real model, so it's a live test. It copies the suites to a temporary folder, starts a real jevtester server there, plays three turns against `decision-1@foundry`, and checks that `play-exploring.yaml` holds `face_danger`, `gather_information`, and `no_move`. It then runs the suite and reports on the run. The first attempt failed on my own test: the run printed "Run 0001 finished: 3 jobs, 3 sent, 0 from cache, 0 failed", but a doubled backslash in my regex, from writing the file through a shell heredoc, kept it from matching. With the regex fixed, all three live tests pass, along with 588 default tests.

## The review

A review subagent spent about 5.5 minutes and 37 tool calls on the step, and found nothing serious. The findings I acted on:

- **A case in the wrong suite.** The context is stored at message time, but the player could change it before moving: send a message in a fight, end the fight with `/adjust fight end`, open the full list with `/moves`, and pick Make Camp. The case would land in `play-fight` with an answer that the fight question doesn't offer, which jevtester would score as a miss for every model. Now a case is saved only when its move was an option in the context it was asked in, and a note says when it isn't.
- **A save that could freeze the screen.** The case is posted on the UI thread with the client's 45-second timeout. The save now waits at most 5 seconds, and catches every network error, including a server that dies mid-reply, which would have crashed the app.
- **Two tests that passed for the wrong reason.** The Escape test pressed Escape last, so nothing could have been saved anyway; it now rolls a move after Escape and checks that only the earlier `no_move` was saved. The failed-request test set the decider to None instead of failing a request; it now covers a decider that raises and a response with no usable answer.
- **`n` with nothing to save.** After a failed request, or with `--no-model`, `n` raised an error. It now logs "No move" and saves a case only when a decision is waiting.
- **What `corrected` means.** The plan defines the tag as overriding "the model's top move", but `cannot_tell` is an abstention, not a move. Overriding it now tags the case `abstained` instead, and the plan says so.

New tests check that an attack is labeled `attack` rather than Strike, that `/vow swear` and `/vow forsake` typed after a message are saved, and the two cases above. All four gates pass with 594 tests, and the three live tests pass.

## Next

Build step 8, assets, which waits on the user's choice of scope.
