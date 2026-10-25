# 01: The scaffold and the rules port

Saturday 24 October 2026, 18:31 to 18:44 PDT. Written by Claude Opus 5.5, the lead agent, with one review subagent.

## The request

The user asked me to read `docs/handoff.md` and begin, to use subagents to review my work as I go, and to keep this diary. The handoff points to `docs/plan.md`, whose build order starts with step 1: a Python 3.14 project with uv, Textual, pydantic v2, and ruamel.yaml; the Datasworn data vendored from the osr-plugins repository at commit `7e2e4a8`; and the rules from the Ironsworn referee plugin's `iron.py` ported into typed functions.

The project is an experiment as much as an app. ironsworn-tui is a terminal app for solo Ironsworn, a tabletop roleplaying game played alone, where the player writes the story and the rules decide how risky actions turn out. A *decision model*, a model that picks among fixed options and reports a probability for each, will read what the player types and suggest which of the game's *moves* (rules triggered by a kind of action, such as Face Danger) applies. The user wants to learn where such models work well, so accuracy measurement matters as much as the app.

The handoff sets rules that shape the work. Tests come before implementation. Four gates run before every commit: `ruff format --check`, `ruff check`, `pyright`, and `pytest`. Findings get fixed in code, never with `noqa`, `type: ignore`, or ignore lists. `main` changes only through pull requests from worktrees.

## What iron.py was

`iron.py` is a 666-line command-line tool. Its job in the plugin is to give Claude deterministic dice math: an agent passes the current state as arguments and gets JSON back. Only two of its functions return values, `action_roll()` and `build_indices()`. Everything else is a `cmd_*` function that prints JSON, and its error helper calls `sys.exit(2)`. Its 458-line test file imports it with a `# noqa: E402` and runs most tests by starting `iron.py` as a subprocess through `uv run`.

So the port is a rewrite with `iron.py` as the reference for the math. I split it into seven modules under `ironsworn_tui/rules/`:

- `dice.py`: the `Hit` enum (miss, weak, strong), challenge dice, and `hit_for()`.
- `action.py`: action rolls and burning momentum.
- `progress.py`: ranks, ticks, and progress rolls.
- `momentum.py`: the momentum range and reset.
- `suffer.py`: Endure Harm and Endure Stress.
- `oracles.py`: the yes/no oracle and table oracles.
- `datasworn.py`: loading and indexing the YAML.

Every roll has two functions: `evaluate_*`, which takes dice that are already rolled, and `roll_*`, which rolls them with a `random.Random` and calls the first. Tests use the first with fixed dice. The plan's momentum burn needs the first, too: burning re-evaluates the existing roll instead of rolling again, so `burn_momentum()` takes an `ActionRoll` and returns a new one against the same challenge dice.

## Places where the port differs from iron.py

Three changes came from reading the data and the rulebook, not from the original code.

**A broken oracle reference.** One row of the settlement name table says to roll on another table, and the data names it `oracle_rollable:classic/settlement/name/landscape_feature`. `iron.py` looked up that string as written, found nothing, and silently rolled on the same table again. The index has the table as `classic/settlement/name/landscape_feature`, so the port strips the `oracle_rollable:` prefix, and a test checks that the sub-roll lands on the landscape feature table.

**The momentum floor.** `iron.py` subtracts harm that spills past 0 health straight from momentum, with no lower limit. The user pointed me to `~/repos/shelf-of-holding`, a corpus of their rulebook PDFs with a search command, and the Ironsworn rulebook's page 13 says: "Your momentum cannot drop lower than -6. ... If a move tells you to lower your momentum, and your momentum is already at its minimum, you will instead make the Face a Setback move." The port stops momentum at -6 and records the rest as `setback` on the result, so the turn loop in build step 5 can trigger Face a Setback.

**Range checks.** `iron.py` accepted a d6 of 7 or a momentum of 15. The port raises `RulesError` for dice outside their faces, momentum outside -6 to +10, meters and stats outside 0 to 5, and progress outside 0 to 40 ticks.

I also read page 12 of the rulebook on burning momentum and decided that `iron.py`'s rule, which sets the action score to the momentum, gave the same result. That was wrong, as the review below found.

## Typing the YAML

pyright in strict mode rejected the first version with 13 errors, almost all about values typed `Any` or unknown from the YAML. ruamel.yaml's `load` method has an untyped parameter, and strict mode reports the method itself as "partially unknown". Declaring the loader as `Any` (`loader: Any = YAML(...)`) clears that without an ignore comment. For the rest, I parse oracle tables into frozen pydantic models (`OracleTable`, `OracleRow`, `RollRange`, `OracleRollDirective`) at load time, which removed `Any` from `oracles.py` entirely. Moves stay as raw YAML for now, because build step 2 builds the typed move catalog.

The data also produced three `ReusedAnchorWarning`s on every test run: `settlement.yaml` defines the anchor `CollectionSource` three times and `path.yaml` defines `objective` twice. YAML allows redefining an anchor, so the loader suppresses that one warning class.

## Verifying it

The first version of the ported suite had 110 tests across six files, and all four gates passed. Every behavior `test_iron.py` checked has an equivalent: hit math, the cap of 10, die cancellation by negative momentum, burning, matches, the five yes/no thresholds and doubles, the Pay the Price table's "roll twice more" row, progress per rank, progress rolls by full boxes, momentum bounds for 0 to 8 debilities, harm and stress spill, the higher of meter and stat, and the fate choice on a miss at 0. The CLI-only tests (the `schema_version` field, metadata stripping, exit codes) have no counterpart, because the port has no CLI.

## The review

I gave a general-purpose subagent the plan, the `iron.py` source, the port, and the rulebook search command, and asked for rules errors, test gaps, and API problems, without telling it what I thought was right. It ran for about 3 minutes and used 14 tool calls. It checked the data with a script of its own: all 38 oracle tables cover their whole die with no gaps, and every sub-roll target resolves.

Its main finding was a bug that both `iron.py` and my port had. The rulebook says that when you burn momentum, you "cancel any challenge dice that are less than your current momentum value", and "the result of the other die stands". The other die stands against the action score you rolled, not against the momentum. Replacing the score with the momentum can make the result worse. The reviewer's example: stat 3, action die 6, so a score of 9, against challenge dice 2 and 8. That's a strong hit. With momentum 3, `burn_momentum` returned a score of 3 against the same dice, a weak hit. The correct result uses the higher of the score and the momentum, which keeps the strong hit. `burn_available` already computed the right answer, so the planned roll card would never have offered that burn, but the function allowed it. I changed `burn_momentum` and added three tests, including the reviewer's example.

I acted on these other findings:

- **One place for momentum changes.** The -6 floor and the setback were inside the Endure Harm code. The outcomes table in build step 5 will apply many momentum gains and losses, so `momentum.py` now has `adjust_momentum(momentum, delta, maximum)`, and the suffer moves use it.
- **The fate choice depends on debilities.** On a miss at 0 health, Endure Harm says to mark wounded or maimed "(if currently unmarked)" or roll on its table. If both are already marked, the player has no choice, and the rules functions don't know about debilities. I renamed `needs_fate_choice` to `fate_triggered` and documented that the caller decides whether the choice exists.
- **Datasworn's `duplicates` field.** The `reroll` loop I ported from `iron.py` never runs, because no row in the data uses `reroll`. The value the data does use is `make_it_worse`, on Pay the Price's 99 to 100 row ("Roll twice more on this table. Both results occur. If they are the same result, make it worse.") and two turning point rows. `OracleResult` now has a `make_it_worse` flag, and a `truncated` flag for rolls cut off at the depth limit of three.
- **Shared mutable data.** `datasworn()` is cached, and its dictionaries could be changed by any caller. The indices are now read-only `MappingProxyType` views, and loading raises if two assets or NPCs share an id.
- **Missing tests**: Endure Stress's floor, setback, and spirit path, momentum already at -6, zero harm, and a parametrized test that each of the 38 tables covers its die.

I deferred three suggestions to the steps that need them: a typed move model (step 2), the stat name on `ActionRoll` (step 5), and parsing a likelihood from player text (step 6).

One slip of my own: the read-only test first used a `# pyright: ignore` comment to assign to the read-only mapping, which the handoff forbids. I replaced it with a `cast`. A `grep` over `ironsworn_tui` and `tests` for `noqa`, `type: ignore`, and `pyright: ignore` now finds nothing.

After the fixes, the suite has 167 tests, 38 of them the parametrized table check, and all four gates pass.

## Next

Build step 2: a typed catalog over the 35 moves, the four move groups, and the three context lists (`exploring` with 19 options, `journey` with 20, and `fight` with 10).
