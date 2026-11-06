# Vendored data

`datasworn/` is copied from the Ironsworn referee plugin in osr-plugins, `plugins/ironsworn-referee/skills/referee/references/datasworn/`, at commit `7e2e4a8`. The plugin vendored it from Datasworn; [`datasworn/LICENSE.md`](datasworn/LICENSE.md) gives the upstream commit and each file's license.

One value differs from the copy. In `truths.yaml`, the second Mysticism option ("Magic is rare and dangerous") covers rolls 34 to 67. The copy gave it 68 to 100, the same as the third option, so no roll picked it. Every other truth splits its three options at 33 and 67.
