-- Grain: one row per experiment, INCLUDING invalid ones.
--
-- Invalid experiments are deliberately retained. Dropping them would hide the
-- archive's single most important quality signal -- that ~22% of it cannot support
-- causal inference. They are excluded from *inferential* comparisons instead, via
-- is_inferentially_eligible.
select
    s.test_id,
    s.partition,
    s.decision,
    s.is_inferentially_eligible,
    s.randomization_unreliable,
    s.attribution_limited,
    s.selected_arm_id,
    s.reference_arm_id,
    s.best_ctr_arm_id,
    s.n_arms,
    s.total_impressions,
    s.pooled_ctr,
    s.srm_pvalue,
    s.omnibus_pvalue,
    s.mde_relative,
    s.bayes_prob_exceeds,
    s.started_at,
    cast(s.started_at as date) as started_date,
    s.start_hour,
    s.power_at_5pct,
    s.power_at_10pct,
    s.power_at_20pct,
    s.power_at_50pct,
    s.required_n_at_5pct,
    s.required_n_at_10pct,
    s.required_n_at_20pct,
    s.required_n_at_50pct,
    s.reasons,
    -- SRM is a DIAGNOSTIC. It is surfaced, never used to invalidate: neither the
    -- intended allocation nor each arm's active duration is recorded.
    (s.srm_pvalue < 0.001)      as srm_flag_diagnostic,
    e.creation_spread_seconds
from {{ source('raw', 'analysis_experiment_stats') }} s
left join {{ ref('int_experiment_arms') }} e on e.test_id = s.test_id
