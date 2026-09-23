# Power BI semantic model

Power BI Desktop does not run on macOS, where this project was built. Rather than ship
an unverifiable `.pbix`, ExperimentGuard delivers the modelled star schema as Parquet
plus this specification, so a report author on Windows can assemble the file in minutes
and get exactly the model the analysis intends.

Run `make export` to produce `exports/*.parquet`.

## Import order

Import dimensions before facts so Power BI infers the relationship directions correctly:

1. `dim_date`
2. `dim_experiment`
3. `dim_arm`
4. `fct_arm_result`
5. `fct_arm_comparison`
6. `fct_experiment_decision`
7. `fct_policy_comparison`

## Grain

| Table | Grain | Notes |
|---|---|---|
| `dim_date` | one calendar day an experiment started | carries `in_cache_misconfiguration_window` |
| `dim_experiment` | one experiment | `test_id` is the key |
| `dim_arm` | one arm (package) | `arm_id` is the key; `is_reference_arm` marks display orientation |
| `fct_arm_result` | one arm | per-arm impressions, clicks, CTR |
| `fct_arm_comparison` | one **ordered** arm pair | K arms produce K×(K−1) rows |
| `fct_experiment_decision` | one experiment, **including INVALID** | one row per experiment, always |
| `fct_policy_comparison` | one experiment × policy | four policies per experiment |

## Relationships

| From | To | Cardinality | Direction |
|---|---|---|---|
| `fct_arm_result[arm_id]` | `dim_arm[arm_id]` | many-to-one | single |
| `fct_arm_result[test_id]` | `dim_experiment[test_id]` | many-to-one | single |
| `fct_arm_comparison[treatment_arm_id]` | `dim_arm[arm_id]` | many-to-one | single (active) |
| `fct_arm_comparison[reference_arm_id]` | `dim_arm[arm_id]` | many-to-one | **inactive** — use `USERELATIONSHIP` |
| `fct_experiment_decision[test_id]` | `dim_experiment[test_id]` | one-to-one | single |
| `fct_experiment_decision[started_date]` | `dim_date[date_day]` | many-to-one | single |
| `fct_policy_comparison[test_id]` | `dim_experiment[test_id]` | many-to-one | single |

`fct_arm_comparison` has two paths to `dim_arm`. Power BI allows only one active
relationship between a pair of tables, so the reference path must be created inactive
and invoked explicitly with `USERELATIONSHIP`.

## Modelling rules that protect the analysis

These are not stylistic preferences; violating them misreports the statistics.

1. **Never average `risk_ratio` across experiments.** A ratio of rates is not additive.
   Aggregate clicks and impressions, then divide (see `CTR` below).
2. **`rr_lo_descriptive` / `rr_hi_descriptive` are descriptive and unadjusted.** Do not
   label them as confidence bounds for the launch decision. The gate is `rejected`,
   which reflects the Holm-adjusted test within each experiment.
3. **Keep INVALID experiments visible.** They are ~22% of the archive and are the
   headline quality finding. Filter with `is_inferentially_eligible` only when a visual
   makes an inferential claim.
4. **Never force a winner.** `selection_status` is `ONE`, `NONE` or `MULTIPLE`; the
   archive's own `winner` column is `NONE` for 76.4% of experiments. Agreement measures
   must divide by the count where *both* policies selected exactly one arm.
5. **`srm_flag_diagnostic` is a diagnostic.** It must not be presented as proof of
   broken randomisation. Use `randomization_unreliable` for that.

## Suggested pages

- **Reliability overview** — decision mix, MDE distribution, share powered at 5/10/20/50%.
- **Randomisation audit** — decisions and imbalance by `started_date` and `start_hour`,
  with `in_cache_misconfiguration_window` highlighted. This reproduces the evidence that
  led the archive's authors to the cache glitch.
- **Policy comparison** — the four policies side by side, with `selection_status` shown
  rather than hidden.
