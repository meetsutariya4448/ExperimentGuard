-- Grain: one row per arm. Descriptive per-arm performance.
select
    p.arm_id,
    p.test_id,
    p.partition,
    p.impressions,
    p.clicks,
    p.ctr,
    p.impressions / nullif(a.total_impressions, 0)  as impression_share,
    1.0 / nullif(a.n_arms, 0)                       as expected_impression_share,
    p.first_place,
    p.winner,
    p.significance                                  as archive_significance,
    (p.clicks = 0)                                  as is_zero_click_arm
from {{ ref('stg_packages') }} p
inner join {{ ref('int_experiment_arms') }} a on a.test_id = p.test_id
