-- The three archive partitions exist to support staged analysis; an experiment
-- appearing in two of them would destroy that guarantee.
select test_id, count(distinct partition) as n_partitions
from {{ ref('dim_arm') }}
group by test_id
having count(distinct partition) > 1
