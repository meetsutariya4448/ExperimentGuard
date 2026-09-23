-- selected_arm_id is populated exactly when selection_status = 'ONE'.
-- NONE and MULTIPLE must never carry a selected arm: that would invent a decision
-- the policy did not make.
select test_id, policy, selection_status, selected_arm_id
from {{ ref('fct_policy_comparison') }}
where (selection_status = 'ONE' and selected_arm_id is null)
   or (selection_status <> 'ONE' and selected_arm_id is not null)
