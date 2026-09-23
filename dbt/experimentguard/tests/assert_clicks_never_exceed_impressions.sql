-- The basic binomial invariant. Any row here is a data or ingestion fault.
select arm_id, clicks, impressions
from {{ ref('fct_arm_result') }}
where clicks > impressions
