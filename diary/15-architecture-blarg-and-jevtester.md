# 15: The architecture doc, Blarg, and jevtester going public

Sunday 25 October 2026, 07:40 to 09:05 PDT. Written by Claude Opus 5.5, the lead agent. Subagents did the drafting, checking, and fixing. I coordinated, merged, and pushed.

## The architecture doc and the thanks

The user asked for "an architecture doc for devs new to the project", and for links to Ironsworn's home page and its DriveThruRPG listing in a thanks section. One subagent drafted `docs/architecture.md`, and a second checked it against the code. The check fixed five errors. One was a claim that only the turn engine and the CLI import the decision code: `app.py` imports `Suggestion` from `policy.py`. The page records three places where the code breaks its own layering, rather than hiding them. One is `outcomes.py`, which imports type aliases from `campaign.py`. The same PR added `/endure` to the idle hint, which the drafter noticed was missing. The thanks section links Tomkin Press's Ironsworn page, the free digital edition, DriveThruRPG product 238369, and Datasworn. That was PR #19.

## Blarg

The user asked to switch the example character to "Blarg (long form Blarg the Destructor) in all the docs and screenshots". A subagent changed the docs, the help examples, and the screenshot script, and regenerated the 8 SVGs, in PR #20. I reported that the `suggest` defaults still said Kira. The user answered: "Fix all references. Tests and diary is fine to keep Kira." PR #21 changed the defaults to "Blarg, the Destructor". The recorded suites and experiment phrasings keep Kira, because the measured results depend on that exact text.

## jevtester

The user chose the same license as this repo, and asked me to fix whatever jevtester needed, write docs as for ironsworn-tui, and publish them. The work went in four stages:

1. **Cleanup, PR #25.** The repo got a license, placeholders for the account details, a `jevtester.local.toml` override, and CI. CI failed at first on four API contract tests. One Brier score differed by one ulp, the smallest step between two float values, between macOS and Linux. The cause was `pow()` in `(p - y) ** 2`. A subagent changed it to `(p - y) * (p - y)`, which rounds the same everywhere.
2. **Docs, PR #26.** Three subagents wrote the user pages, the reference pages, and the site with 13 screenshots, all in one worktree. A fourth checked every page against the code. It also confirmed 10 known issues, which went into jevtester's handoff.
3. **The history scrub.** A subagent rewrote the history in a scratch clone. Its replacements covered the account ID, the resource name, the resource group, and the subscription, region, and quota details. I checked the result myself. The final tree matched main, no matches remained, and the count was still 89 commits. Claude Code's auto mode blocked my first force-push. I gave the user the commands, and they asked me to run them. Main went from `0157af4` to `672cc18`, and 23 merged branches were deleted.
4. **Going public.** jevtester is public, and https://mmacy.github.io/jevtester/ is live. GitHub keeps each pull request's refs, so old PR diffs in both repos can still show the scrubbed values. Only GitHub Support can purge them.
