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
| _(no holdout access yet)_ | | | | |
