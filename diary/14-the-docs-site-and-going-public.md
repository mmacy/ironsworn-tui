# 14: The docs site and going public

Sunday 25 October 2026, 06:59 to 07:32 PDT. Written by Claude Opus 5.5, the lead agent, with three subagents: one built the site, and two audited ironsworn-tui and jevtester for publication.

## The request

While I fixed the issues in entry 13, the user asked: "Ensure the docs have screenshots, and we should get a Zensical publishing pipeline together and publish on merge to main to GH Pages. I'd like to flip the project to public if it's ready." Zensical is a static site generator from the Material for MkDocs team.

## The site and the screenshots

A subagent built the site in its own worktree:

- `zensical.toml` groups the nav by Diataxis, with a Development section.
- `docs/index.md` is a home page adapted from the README.
- `.github/workflows/docs.yml` builds with uv and deploys to GitHub Pages on every push to main.
- Zensical is pinned at 0.0.69.

The build found two broken links to `experiments/results.md`, which sits outside `docs/`. They now point to GitHub.

The screenshots come from `scripts/screenshots.py`. It drives the real app headlessly with Textual's pilot, loaded dice, and the fixture decider, so it makes no model calls. Two runs gave byte-identical SVGs. After I rebased the branch onto entry 13's fixes, I reran the script, and only the move list changed, because it now ends with Aid Your Ally. That was PR #15. Its first deploy failed at `actions/configure-pages` with "Get Pages site failed", as expected, because Pages wasn't on yet.

## The readiness audit

A read-only subagent audited the full history of ironsworn-tui. It found no secrets. It did find:

- Three things to fix: the docs sent readers to jevtester, which was private; `jevtester.toml` named the user's Cloudflare account ID and Azure Foundry resource; and the vendored Datasworn `LICENSE.md` still said "this plugin".
- Two smaller ones: an SSH-only clone command, and no Ironsworn trademark notice.

PR #16 fixed the small items. I asked the user three questions, and they chose to make jevtester public too, to replace the two identifiers with placeholders and rewrite history, and to go public with Pages.

## Placeholders and the history rewrite

jevtester can't merge two config files. Its audit showed that it reads `--config`, then `$JEVTESTER_CONFIG`, then `./jevtester.toml`. So the fix lives in ironsworn-tui instead. `load_settings` now uses `jevtester.local.toml` when it exists, and that file is gitignored. The committed `jevtester.toml` has `<your Cloudflare account ID>` and `<your Foundry resource>`. I copied the user's real file to `jevtester.local.toml` before merging, so their setup kept working. That was PR #17.

Next, I ran `git filter-repo --replace-text` on a fresh clone. The two values had appeared only in `jevtester.toml`. After the rewrite, `git grep` across all 20 commits found neither value. The final tree hash, `8acbc494`, matched main's before the rewrite. I force-pushed main, from `b56b18f` to `f608774`. GitHub keeps each pull request's refs, so PR #3's old diff can still show the values. Only GitHub Support can purge those.

## Going public

I made the repo public, turned on Pages with `build_type=workflow`, and reran the docs workflow. It succeeded, and https://mmacy.github.io/ironsworn-tui/ returns 200, as do its pages and screenshots. I also set the repo's homepage and description, and turned on delete-branch-on-merge.

## jevtester

The jevtester audit found no credentials in 80 commits, but it isn't ready yet:

- It has no LICENSE file, so strangers have no right to use it.
- It names the same two identifiers in more places, including test fixtures.
- It also names a resource group, links two other private repos, and has 24 stale branches.

The user had asked to hear these findings before jevtester goes public. Until it does, the docs' links to it lead to a 404.
