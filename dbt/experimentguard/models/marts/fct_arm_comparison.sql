-- Grain: one row per ORDERED arm pair.
--
-- Risk ratios, their descriptive intervals, and the Holm-adjusted p-values come from
-- the Python analysis layer. The intervals here are DESCRIPTIVE and unadjusted: the
-- decision gate is `rejected`, which reflects the multiplicity-adjusted test. An
-- unadjusted interval must never be read as a family-wise bound.
select
    c.test_id,
    c.partition,
    c.treatment_arm_id,
    c.reference_arm_id,
    p.treatment_clicks,
    p.treatment_impressions,
    p.treatment_ctr,
    p.reference_clicks,
    p.reference_impressions,
    p.reference_ctr,
    c.risk_ratio,
    c.rr_lo                 as rr_lo_descriptive,
    c.rr_hi                 as rr_hi_descriptive,
    c.p_value               as p_value_unadjusted,
    c.p_adjusted,
    c.rejected,
    c.rr_estimable,
    c.note
from {{ source('raw', 'analysis_arm_comparison') }} c
left join {{ ref('int_arm_pairs') }} p
    on  p.test_id = c.test_id
    and p.treatment_arm_id = c.treatment_arm_id
    and p.reference_arm_id = c.reference_arm_id
