-- The reference arm must be exactly one per experiment, or uplift displays are
-- ambiguous. The tie-break on arm_id exists precisely to guarantee this.
select test_id, count(*) as n_reference_arms
from {{ ref('dim_arm') }}
where is_reference_arm
group by test_id
having count(*) <> 1
