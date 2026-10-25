# Vendored Datasworn data — license and attribution

The YAML files in this directory are vendored from the [Datasworn](https://github.com/rsek/datasworn) project, which provides Ironsworn game rules in structured form.

## Source

- **Upstream:** [rsek/datasworn](https://github.com/rsek/datasworn)
- **Tag:** `v0.1.0-prerelease`
- **Commit SHA:** `e643a75263c1cb3e845a0c0789879ff4e8b49532`
- **Vendored from:** `source_data/classic/`

## Original work

*Ironsworn* is by **Shawn Tomkin** (2018). Rulebook and SRD: [ironswornrpg.com](https://ironswornrpg.com).

## Per-file licensing

The Datasworn project mixes two Creative Commons licenses depending on the source rulebook content each file derives from.

### CC BY 4.0

Files under the [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0) license:

- `moves.yaml`
- `rules.yaml`
- `assets/combat_talent.yaml`
- `assets/companion.yaml`
- `assets/path.yaml`
- `assets/ritual.yaml`
- `oracles/action_and_theme.yaml`
- `oracles/character.yaml`
- `oracles/name.yaml`
- `oracles/place.yaml`
- `oracles/settlement.yaml`
- `oracles/turning_point.yaml`

### CC BY-NC-SA 4.0

Files under the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-nc-sa/4.0) license:

- `atlas.yaml`
- `npcs.yaml`
- `truths.yaml`

Each YAML file records its own license in its `_source.license` field.

## Distribution license for this directory

Because some files in this directory are licensed under CC BY-NC-SA 4.0, the **directory as a whole is distributed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0)** — the most restrictive constraint applies. Re-users must:

1. Provide attribution to Shawn Tomkin and link to [ironswornrpg.com](https://ironswornrpg.com).
2. Not use this data for commercial purposes.
3. Distribute derivative works under the same license.

The Python scripts and skill prompts elsewhere in this plugin are original work and are not subject to this license — see the plugin root for their licensing.

## How to re-vendor

```bash
git clone --branch v0.1.0-prerelease https://github.com/rsek/datasworn.git ~/repos/datasworn
cp -r ~/repos/datasworn/source_data/classic/. plugins/ironsworn-referee/skills/referee/references/datasworn/
```

Update the commit SHA above if upstream advances. Re-run the license audit (`grep -E '^\s*license:' *.yaml oracles/*.yaml assets/*.yaml`) and update the per-file lists if upstream re-licenses any file.
