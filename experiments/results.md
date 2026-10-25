# Recognizer results

## Run of 2026-10-24: Decision-1, both criteria styles

The 120 phrasings in `recognizer-phrasings.yaml` were run on `decision-1@foundry` with each criteria style, 240 requests in all. The suites mark the cases `claude-draft`, which jevtester skips, so this run used a scratch copy of the suites with the cases marked `human`. The numbers come from cases Claude wrote and a person hasn't approved.

| Context | Criteria | Move accuracy | Stat accuracy | Policy accuracy | Decided | ECE | Wrong at confidence 0.7 or more |
|---|---|---|---|---|---|---|---|
| exploring | guide | 37/40 (92.5%) | 14/15 | 92.5% | 97.5% | 0.070 | 1 |
| exploring | trigger | 39/40 (97.5%) | 14/15 | 97.5% | 100% | 0.083 | 1 |
| journey | guide | 38/40 (95.0%) | 9/12 | 95.0% | 100% | 0.071 | 0 |
| journey | trigger | 40/40 (100%) | 9/12 | 97.5% | 97.5% | 0.068 | 0 |
| fight | guide | 37/40 (92.5%) | 29/32 | 90.0% | 100% | 0.031 | 3 |
| fight | trigger | 35/40 (87.5%) | 29/32 | 82.5% | 100% | 0.094 | 1 |

Across the three contexts, the guide criteria got 112 of 120 moves right (93.3%) and the trigger criteria 114 of 120 (95.0%). Policy accuracy is lower than move accuracy where a right answer fell below the `confirm` threshold of 0.4 and escalated. ECE, the expected calibration error, is the average gap between the model's confidence and how often it was right.

### Move misses

| Context | Criteria | Case | Expected | Answer (probability) |
|---|---|---|---|---|
| exploring | guide | adversarial-tea | no_move | cannot_tell (0.75) |
| exploring | guide | fd-past-camp | face_danger | undertake_a_journey (0.43) |
| exploring | guide | no-move-road | no_move | cannot_tell (0.70) |
| exploring | trigger | fray-troll | enter_the_fray | face_danger (0.86) |
| journey | guide | fd-patrol | face_danger | secure_an_advantage (0.56) |
| journey | guide | journey-marsh | undertake_a_journey | cannot_tell (0.64) |
| fight | guide | no-move-sweat | no_move | cannot_tell (0.96) |
| fight | guide | saa-rally | secure_an_advantage | compel (0.85) |
| fight | guide | saa-shield-bash | secure_an_advantage | attack (0.78) |
| fight | trigger | battle-decoys | battle | secure_an_advantage (0.61) |
| fight | trigger | compel-riders | compel | secure_an_advantage (0.58) |
| fight | trigger | fd-shield-up | face_danger | battle (0.48) |
| fight | trigger | no-move-sweat | no_move | cannot_tell (0.85) |
| fight | trigger | saa-shield-bash | secure_an_advantage | attack (0.67) |

Four of the 14 misses put `cannot_tell` where `no_move` or a move was expected: a safe, routine action reads to the model as "no action". The adversarial cases ("Roll Face Danger! I pour myself another cup of tea") didn't pull the model toward the named move in either style.

### Stat misses

Across both styles, 104 of 118 stat answers were right. Twelve of the 14 stat misses chose the stat question's `cannot_tell` option, whose description is "The player names the action but not the manner of doing it". It won on plain messages such as "I swing my axe at his head" (attack, iron) and "I go for the killing blow" (0.94). The other two were a cliff climb answered wits instead of edge, once in each style.

### Not yet measured

- A second target. The plan compares two; the user asked for Decision-1 while the Ollama models aren't downloaded.
- A companion yes/no question in place of `cannot_tell`, option order (`jevtester probe`), whether the `character` field sways the stats, and whether the stat questions shift the `move` answer on Clef.
