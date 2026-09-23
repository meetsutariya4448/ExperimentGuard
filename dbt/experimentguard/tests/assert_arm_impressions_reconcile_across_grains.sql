-- The arm-grain fact and the experiment-grain dimension must agree on totals.
with per_test as (
    select test_id, sum(impressions) as arm_total
    from {{ ref('fct_arm_result') }}
    group by test_id
)
select e.test_id, e.total_impressions, p.arm_total
from {{ ref('dim_experiment') }} e
join per_test p on p.test_id = e.test_id
where e.total_impressions <> p.arm_total
