-- Invalid experiments must remain in the decision fact -- excluded from inference,
-- not from the warehouse. An experiment present in dim_experiment but missing a
-- decision row would mean the engine silently dropped it.
select e.test_id
from {{ ref('dim_experiment') }} e
left join {{ ref('fct_experiment_decision') }} d on d.test_id = e.test_id
where d.test_id is null
  and e.partition in (select distinct partition from {{ ref('fct_experiment_decision') }})
