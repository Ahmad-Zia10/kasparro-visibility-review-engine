# Evaluation report

Prompt `classify_v1`, model `qwen2.5:3b`. Outputs are replayed from the saved local-model run, so this checks those outputs only; replay itself does not establish model quality.

## Split: tune

Cases 6, graded 5, failed 1, skipped 0.

| Label | Model agreement | Model P / R | Baseline agreement | Baseline P / R |
|---|---|---|---|---|
| mentioned | 1.0 | 1.0 / 1.0 | 1.0 | 1.0 / 1.0 |
| recommended | 0.4 | 0.5 / 0.333 | 0.667 | 0.667 / 0.667 |
| negative | 0.8 | 1.0 / 0.5 | 0.667 | 0.667 / 0.667 |
| position | 0.6 | None / None | 0.833 | None / None |

## Split: final

Cases 9, graded 4, failed 5, skipped 0.

| Label | Model agreement | Model P / R | Baseline agreement | Baseline P / R |
|---|---|---|---|---|
| mentioned | 0.75 | 0.75 / 1.0 | 1.0 | 1.0 / 1.0 |
| recommended | 0.5 | 1.0 / 0.333 | 1.0 | 1.0 / 1.0 |
| negative | 0.5 | None / 0.0 | 0.778 | 0.5 / 0.5 |
| position | 0.75 | None / None | 1.0 | None / None |

## Split: all

Cases 15, graded 9, failed 6, skipped 0.

| Label | Model agreement | Model P / R | Baseline agreement | Baseline P / R |
|---|---|---|---|---|
| mentioned | 0.889 | 0.875 / 1.0 | 1.0 | 1.0 / 1.0 |
| recommended | 0.444 | 0.667 / 0.333 | 0.867 | 0.857 / 0.857 |
| negative | 0.667 | 1.0 / 0.25 | 0.733 | 0.6 / 0.6 |
| position | 0.667 | None / None | 0.933 | None / None |

## Checks

- Failed classifications: {'a3fdd8bb-bcd9-4608-9786-ad4b3a2c7dc2': 'Value error, no evidence for mentioned', 'd5043498-a516-463e-b97b-5fc917f5e26a': 'Value error, no evidence for mentioned', '58034df8-0d67-4878-827a-376afa1efc2b': 'no verified quote: Value error, no evidence for mentioned', 'e2bb9e59-578d-474c-b7e1-ee8c29b36d90': 'Value error, no evidence for mentioned', '5beb2a32-6c6c-42d8-861c-9fc9680b9930': 'Value error, no evidence for mentioned', 'edge-injection-1': 'Value error, no evidence for mentioned'}
- Score arithmetic mismatches against the hand-written formula: none
- Diagnostic evidence problems: none
- Planted unsupported claim flagged: ['X1: excerpt not in evidence of a3fdd8bb-bcd9-4608-9786-ad4b3a2c7dc2']
- Competitor lists naming Kasparro, before / after the fix: 2 / 0
- Repeat runs (R69): not run. One local call takes 60 to 140 seconds on this CPU.
