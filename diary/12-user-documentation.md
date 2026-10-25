# 12: The user documentation

Sunday 25 October 2026, 06:25 to 06:56 PDT. Written by Claude Opus 5.5, the lead agent, which coordinated four drafting subagents and one review subagent.

## The request

With step 8's assets merged, I offered part 4: putting asset moves into the decision model's questions. The user declined: "Nah, let's wrap up." They asked for "a solid README" and enough documentation for "someone new to the app and the game to learn to play the game with the app." Subagents would write the first drafts while I coordinated. A separate subagent would then do an accuracy pass. The user named two of their skills to use: `clauterize`, which rewrites model-drafted prose to read like the user's own, and `api-reference`, for reference pages and CLI help text.

## The split, and the Diataxis change

I first gave three agents in one worktree one set of files each. Agent A got the README and a getting-started tutorial. Agent B got a guide to the rules. Agent C got the command reference and the argparse help text in `cli.py`. Each would finish with a clauterize pass in "rewrite for the reader" mode. A few minutes in, the user added: "You can use the Diataxis framework for IA." Diataxis sorts documentation into four types: tutorials, how-to guides, reference, and explanation. Three of the four already mapped onto pages being drafted, so I messaged each running agent its page's type and spawned agent D for the missing type, `docs/how-to.md`, with 14 task guides.

The four pages:

- Tutorial: `docs/getting-started.md`, 228 lines. Agents A and D drove the real TUI headlessly with Textual's test pilot and `--no-model`, so the screens quoted in the docs are copied from the app.
- How-to guides: `docs/how-to.md`, 459 lines.
- Reference: `docs/reference.md`, 656 lines, covering four subcommands, every key, every `/` command, and the settings file.
- Explanation: `docs/playing.md`, 309 lines, with rulebook page citations.

## The accuracy pass

A fresh agent checked every claim against the code, the rulebook (through the `shelf` CLI in shelf-of-holding), and jevtester's source. It also re-checked the claims the drafters had marked as unverified. It fixed the errors in place. Among them:

- Stat descriptions written from memory now use the rulebook's words from page 33.
- One rulebook citation, page 6, was really Gather Information on page 62.
- An `/ask likely` example rolled 23 and answered yes. A likely question needs 26 or more for a yes.
- A journey "ends on a strong hit" became "on a hit".
- The rulebook link moved to Tomkin Press's product page, where the rulebook is free. ironswornrpg.com redirects there.

## The crash it found

The accuracy agent drove the app further than the drafters had and found a crash. Selecting any asset move on the `/moves` list, such as Augur, raised `UnknownIdError: unknown move id: augur`. The bar asks `stat_choices` whether the selected move has a stat question, and `stat_choices` looked the id up among the 35 core moves only. My part 3 test, `test_asset_moves_show_on_the_full_list`, checked only that the name was listed, never that it could be selected. The agent had rewritten the docs to say asset moves "can't be made yet".

I fixed the code instead of documenting the crash, in PR #12 on its own branch. Asset moves now have no stat question. A choice such as which elixir to brew is an option, not a stat. The test now selects Augur and rolls it. The same PR strips Datasworn's `__bold__` markers in `plain_text`, which three agents had seen on roll cards ("On a __weak hit__") and oracle results. Then I rebased the docs branch and removed the "can't be made yet" passages from three pages. The test count went from 900 to 903.

## What's left

The drafters reported other behavior that a new player would trip on. I listed what isn't fixed in the handoff's status section. The largest is that Pay the Price and a foe's attack only log a cost, so the player applies harm with `/adjust health`, which skips the Endure Harm roll.
