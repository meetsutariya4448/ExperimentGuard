# Holdout Access Log

The Upworthy Research Archive ships three mutually exclusive partitions so that a policy can be
developed, validated, and then evaluated once without contaminating the result.

ExperimentGuard honours that design:

1. **exploratory** — all policy and threshold development.
2. **confirmatory** — validation of the frozen policy.
3. **holdout** — opened **once**, for final evaluation only.

Reading the holdout partition requires `--partition holdout --confirm-final` and appends an
entry below. `tests/test_partition_discipline.py` fails if any default code path reads holdout.

| Date | Policy version | Policy SHA-256 | Reason | Operator |
|------|----------------|----------------|--------|----------|
| 2026-09-23 | 1.0.0 | 096283cbe23ba8af... | final evaluation | ingest CLI |

---

## Evaluation record — 2026-09-23

Complete record of the single holdout evaluation, preserved verbatim.

| Field | Value |
|---|---|
| Started (UTC) | 2026-09-23T04:17:38Z |
| Completed (UTC) | 2026-09-23T04:22:xx Z (see run log) |
| Command | `make holdout` → `python -m experimentguard.analyze --partition holdout --confirm-final` |
| Policy version | 1.0.0 |
| Policy SHA-256 | `096283cbe23ba8af52353bdd4981c3bdb06c641d06dfb0f172f7c25c600be5a7` |
| Pre-holdout commit | `44b6911360be90a78ac697a4a9fae7eac66797a2` |
| Errors | none — exit code 0 |

### Run output

```text
Analysing 4,871 experiments in 'holdout' ...
  2,000/4,871
  4,000/4,871
  wrote 4,871 rows to analysis_experiment_stats
  wrote 75,414 rows to analysis_arm_comparison
  wrote 19,484 rows to analysis_policy_selection
  recorded holdout access in policy/HOLDOUT_LOG.md

Decision mix for 'holdout':
  CONTINUE               3,697  (75.90%)
  INVALID                1,059  (21.74%)
  LAUNCH                   115  ( 2.36%)

  median MDE (eligible): 75.2%
```

### Metrics

| Metric | Holdout (4,871 experiments) |
|---|---|
| CONTINUE | 3,697 (75.90%) |
| INVALID | 1,059 (21.74%) |
| LAUNCH | 115 (2.36%) |
| NO_MEANINGFUL_WIN | 0 (0.00%) |
| Unreliable randomisation | 1,059 (21.74%) |
| ATTRIBUTION_LIMITED | 332 |
| Median MDE (eligible) | 75.2% |

### Notes

- The policy was **not** modified before, during or after this evaluation. Its checksum is
  unchanged from the pre-holdout commit `44b6911`, and `tests/test_frozen_policy.py` asserts it.
- The `Operator` column in the table above reads "ingest CLI". That is a cosmetic mislabel in
  `analyze._log_holdout_access`; the evaluation was run through the **analyze** CLI as shown in
  the Command row. The recorded row is left unaltered rather than rewritten after the fact.
- This partition must not be evaluated again. Any further run would no longer be a holdout.
