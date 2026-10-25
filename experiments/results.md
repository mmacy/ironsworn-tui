# Recognizer results

## Oracle questions of 2026-10-25: Decision-1

When the player types `/oracle` and a question with no table, the app asks the decision model three questions in one request: `kind` (`yes_no`, `table`, or `cannot_tell`), `likelihood` (five options), and `table` (the 22 tables the player rolls). Every question has 26 options or fewer, so no category question comes first.

The 56 questions in `oracle-phrasings.yaml` have known answers: 21 yes or no questions, at least 4 for each likelihood; 33 table questions, at least one for each table; and 2 questions that aren't about the story. Ambiguous questions list the other answers that count, such as `unlikely` for a `small_chance` question, and one question ("Are the riders friend or foe?") accepts either kind. One table question ("How many raiders are in the camp?") has no fitting table. The user approved the experiment, and Claude wrote the questions.

The suite ran twice on `decision-1@foundry`, once per question set, with no repeats: 112 requests.

| Run | `table` question | Kind | Likelihood, acceptable | Likelihood, exact | Table, fitting | ECE kind / likelihood / table | p50 / p95 latency |
|---|---|---|---|---|---|---|---|
| 0001 | with `cannot_tell` | 56/56 | 19/21 (90.5%) | 14/21 (66.7%) | 26/33 (78.8%) | 0.011 / 0.285 / 0.163 | 419 / 641 ms |
| 0002 | without `cannot_tell` | 56/56 | 19/21 (90.5%) | 14/21 (66.7%) | 30/33 (90.9%) | 0.010 / 0.315 / 0.103 | 386 / 586 ms |

The kind was right for all 21 yes or no questions, all 33 table questions, and both questions that aren't about the story. The table count is over the 33 questions a table fits, including the friend-or-foe question's table answer. Play sends run 0002's question set.

### Findings

- **The kind is reliable.** Every kind answer was right in both runs. The lowest confidence was 0.51 in run 0001 and 0.63 in run 0002, both for the friend-or-foe question, which accepts either kind. The rest were 0.83 or more.
- **A `cannot_tell` option on the `table` question hurt.** In run 0001 it won all 7 table misses, such as "What's the child's name?" (`cannot_tell` 0.75, `ironlander-name` 0.24). Without it, 4 of those 7 got the right table at 0.53 or more. This repeats the move experiment, where a `cannot_tell` option on the stat questions won most stat misses.
- **The model doesn't abstain on a question no table fits.** Without the option, "How many raiders are in the camp?" got `challenge-rank` at 0.69.
- **The likelihood is close, but rarely extreme.** In run 0002, the 6 likelihoods at 0.8 or more were all acceptable, and 5 were exact. Of the 7 inexact likelihoods, 6 were one step from the expected one, and 3 of the 4 `small_chance` questions got `unlikely`. The two misses came at low probability: "I doubt they left anything, but is there food in the cart?" got `likely` (0.30), so the model missed the wording, and "Is anyone still at the farm?" after smoke rose from the chimney an hour ago got `fifty_fifty` (0.31).
- **Calibration differs by question.** In run 0002, likelihoods at 0.4 or more were acceptable 18 of 18 times, and 1 of 3 below. Tables at 0.8 or more were right 27 of 28 times, and 1 of 3 from 0.6 to 0.8. The likelihood's ECE of 0.315 is high because the model spreads its probability over neighboring likelihoods that the suite also accepts.

### Table misses in run 0002

| Case | Question | Expected | Answer (probability) |
|---|---|---|---|
| tb-rider-who | Who is the rider? | role | ironlander-name (0.85) |
| tb-elder-trade | What did the elder do before she led the village? | role | action (0.65) |
| amb-friend-or-foe | Are the riders friend or foe? | role, goal, or descriptor | plot-twist (0.78) |
| amb-how-many | How many raiders are in the camp? | no table | challenge-rank (0.69) |

The friend-or-foe question's kind was `yes_no`, so play offers its likelihood, `fifty_fifty` (0.46), which is right.

### Thresholds

The oracle policy, `suites/policies/oracle.yaml`, preselects the first option when the `kind` confidence is at least `act` and the chosen likelihood's or table's probability is at least `pick`. With `act` 0.5 and `pick` 0.4, on run 0002:

| Result | Questions |
|---|---|
| Preselected, and acceptable | 48 (18 likelihoods, 30 tables) |
| Preselected, and wrong | 3 (rider, elder, how many) |
| Nothing preselected | 3 yes or no questions, 2 of them wrong |
| Nothing preselected, as expected | 2 questions that aren't about the story |

`act` is below every kind confidence measured. `pick` at 0.4 keeps both wrong likelihoods from being preselected, and only one right likelihood (0.33) loses its preselection. No `pick` up to 0.6 removes a wrong table, because the wrong tables had 0.65 or more. jevtester's policy accuracy for run 0002 is 0.804 (45 of 56), because it counts only each case's main expected action, not the other acceptable answers.

The player always confirms. Enter rolls a preselected option, and every other table and likelihood is on the bar with its key.

### Cost

jevtester has no price for Foundry, so the cost of the 112 requests is unknown. The move experiment's 480 Clef-flash requests cost $0.0288 on Workers AI.

## Second run of 2026-10-24: two targets and the abstain experiments

After the first run, the user approved the 120 cases and asked for a second target. This run used the approved suites directly, on `decision-1@foundry` and `clef-flash@workers-ai`. Two cases changed from the first run: Battle became an option in `exploring` and `journey`, and one Face Danger case in each was replaced with a Battle case. Each suite ran once per target, with no repeats.

Four ways of asking were compared, each on all 120 phrasings:

- `guide` and `trigger`: the two criteria styles, with no `cannot_tell` option on the stat questions. This is what play now sends, with the guide criteria.
- `guide-stat-abstain`: the guide criteria, with a `cannot_tell` option on each stat question, as the first run had.
- `guide-acts`: like `guide-stat-abstain`, but the `move` question's `cannot_tell` option is replaced by a yes/no question, "Does `player_says` describe something the character does?" A `cannot_tell` case counts as right when that answer is no, and any other case when it's yes and the move is right.

| Variant | Decision-1 move | Decision-1 stat | Clef-flash move | Clef-flash stat |
|---|---|---|---|---|
| guide | 115/120 (95.8%) | 58/59 (98.3%) | 107/120 (89.2%) | 56/59 (94.9%) |
| trigger | 112/120 (93.3%) | 58/59 (98.3%) | 101/120 (84.2%) | 56/59 (94.9%) |
| guide-stat-abstain | 115/120 (95.8%) | 53/59 (89.8%) | 108/120 (90.0%) | 54/59 (91.5%) |
| guide-acts | 110/120 (91.7%) | 53/59 (89.8%) | 84/120 (70.0%) | 51/59 (86.4%) |

By context, for the `guide` variant:

| Context | Target | Move accuracy | Policy accuracy | Decided | ECE | p50 latency |
|---|---|---|---|---|---|---|
| exploring | Decision-1 | 38/40 (95%) | 95.0% | 100% | 0.053 | 483 ms |
| exploring | Clef-flash | 35/40 (87.5%) | 77.5% | 82.5% | 0.187 | 652 ms |
| journey | Decision-1 | 40/40 (100%) | 97.5% | 100% | 0.048 | 445 ms |
| journey | Clef-flash | 35/40 (87.5%) | 80.0% | 90.0% | 0.213 | 602 ms |
| fight | Decision-1 | 37/40 (92.5%) | 90.0% | 100% | 0.028 | 482 ms |
| fight | Clef-flash | 37/40 (92.5%) | 85.0% | 95.0% | 0.229 | 531 ms |

### Findings

- **Both targets clear the 80 percent bar on `exploring`:** Decision-1 at 95 percent and Clef-flash at 87.5 percent.
- **The guide criteria beat the trigger text on both targets,** by 3 cases on Decision-1 and 6 on Clef-flash. Play uses the guide criteria.
- **Dropping the stat `cannot_tell` option helped on both targets.** Decision-1's stat accuracy rose from 53 to 58 of 59, and Clef-flash's from 54 to 56. Play sends stat questions without it.
- **The `acts` question hurt on both targets.** It answered no for many real actions: Decision-1 gave 0.22 to "The wyvern is dead. My vow to avenge my brother is done." and 0.11 to the canyon ambush. Clef-flash said no to 26 real actions, with probabilities of yes from 0.14 to 0.50, so it was rarely sure either way. Play keeps the `cannot_tell` option on the `move` question.
- **Clef-flash's confidence is less calibrated:** ECE of 0.19 to 0.23, against 0.03 to 0.05 for Decision-1. With the same thresholds, its policy escalated 5 to 17.5 percent of cases. Its thresholds need tuning on their own, as the plan says.
- **Whether the stat questions change the `move` answer is unsettled.** Between `guide-stat-abstain` and `guide`, Decision-1 changed no `move` choice and Clef-flash changed one (`battle-decoys`). On both, the probability of the chosen move moved by up to 0.09, and once by 0.25 on Clef-flash. One run of each can't separate that from run-to-run variation.
- **Cost:** the 480 Clef-flash requests in the 960 cost $0.0288 on Workers AI. jevtester has no price for Foundry.

## First run of 2026-10-24: Decision-1, both criteria styles

This run came before the cases were approved and before Battle joined `exploring` and `journey`, so its cases differ slightly from the second run's.

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

## Not yet measured

- Option order, with `jevtester probe`.
- Whether the `character` field sways the stat answers.
- Acting on the ratio of the top two probabilities as well as confidence.
- Run-to-run variation, with `--repeats`.
