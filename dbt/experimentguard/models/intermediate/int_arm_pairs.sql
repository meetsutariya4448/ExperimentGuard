-- Every ORDERED pair of arms within an experiment.
--
-- Ordered, not unordered: the decision rule asks whether a given arm beats every
-- other arm, which is a directional question, so (a -> b) and (b -> a) are distinct
-- comparisons. A K-arm experiment therefore yields K*(K-1) rows.

with arms as (

    select * from {{ ref('stg_packages') }}

)

select
    t.test_id,
    t.partition,
    t.arm_id            as treatment_arm_id,
    r.arm_id            as reference_arm_id,
    t.clicks            as treatment_clicks,
    t.impressions       as treatment_impressions,
    t.ctr               as treatment_ctr,
    r.clicks            as reference_clicks,
    r.impressions       as reference_impressions,
    r.ctr               as reference_ctr
from arms t
inner join arms r
    on t.test_id = r.test_id
   and t.arm_id <> r.arm_id
