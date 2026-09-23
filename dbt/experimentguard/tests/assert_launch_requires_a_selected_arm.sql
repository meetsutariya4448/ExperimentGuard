-- A LAUNCH without a selected arm is incoherent, as is a selected arm without one.
select test_id, decision, selected_arm_id
from {{ ref('fct_experiment_decision') }}
where (decision = 'LAUNCH' and selected_arm_id is null)
   or (decision <> 'LAUNCH' and selected_arm_id is not null)
