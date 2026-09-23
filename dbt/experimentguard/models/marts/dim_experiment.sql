-- Grain: one row per experiment.
select
    a.test_id,
    a.partition,
    a.reference_arm_id,
    a.n_arms,
    a.total_impressions,
    a.total_clicks,
    a.pooled_ctr,
    a.started_at,
    cast(a.started_at as date)      as started_date,
    a.start_hour,
    a.creation_spread_seconds,
    a.n_distinct_headlines,
    a.n_distinct_eyecatchers,
    a.attribution_limited,
    a.has_zero_click_arm,
    a.all_arms_zero_clicks,
    h.headline                      as reference_headline
from {{ ref('int_experiment_arms') }} a
left join {{ ref('stg_packages') }} h
    on h.arm_id = a.reference_arm_id
