-- INVALID and is_inferentially_eligible must never co-occur.
select test_id, decision, is_inferentially_eligible
from {{ ref('fct_experiment_decision') }}
where decision = 'INVALID' and is_inferentially_eligible
