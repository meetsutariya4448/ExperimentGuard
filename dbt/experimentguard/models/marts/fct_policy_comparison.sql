-- Grain: one row per (experiment, policy).
--
-- Long format so the four policies can be compared without assuming each produces a
-- selection. selection_status is ONE, NONE or MULTIPLE, and selected_arm_id is null
-- unless exactly one arm was chosen. Measured across the archive, the archive's own
-- `winner` column is NONE for 76.4% of experiments, so forcing a selection would
-- fabricate decisions that were never recorded.
select
    s.test_id,
    s.partition,
    s.policy,
    s.selection_status,
    s.selected_arm_id,
    s.selection_count,
    s.is_inferentially_eligible,
    d.decision                              as experimentguard_decision,
    (s.selection_status = 'ONE')            as made_a_selection,
    r.ctr                                   as selected_arm_ctr,
    d.pooled_ctr
from {{ source('raw', 'analysis_policy_selection') }} s
left join {{ ref('fct_experiment_decision') }} d on d.test_id = s.test_id
left join {{ ref('stg_packages') }} r on r.arm_id = s.selected_arm_id
