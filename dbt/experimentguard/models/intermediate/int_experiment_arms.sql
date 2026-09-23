-- Experiment-level shape, plus the deterministic reference arm.
--
-- The reference arm is the earliest-created arm, ties broken by arm_id. It exists so
-- that displays and uplift charts have a stable orientation. It is NOT a control:
-- the archive's authors report that Upworthy used no control-group concept, so
-- beating this arm establishes nothing on its own, and no decision depends on it.

with arms as (

    select * from {{ ref('stg_packages') }}

),

ranked as (

    select
        *,
        first_value(arm_id) over (
            partition by test_id
            order by created_at, arm_id
            rows between unbounded preceding and unbounded following
        )                                                                as reference_arm_id,
        row_number() over (partition by test_id order by created_at, arm_id) as arm_ordinal
    from arms

),

rolled as (

    select
        test_id,
        partition,
        any_value(reference_arm_id)                              as reference_arm_id,
        count(*)                                                 as n_arms,
        sum(impressions)                                         as total_impressions,
        sum(clicks)                                              as total_clicks,
        sum(clicks) / nullif(sum(impressions), 0)                as pooled_ctr,
        min(created_at)                                          as started_at,
        max(created_at)                                          as last_arm_created_at,
        date_diff('second', min(created_at), max(created_at))     as creation_spread_seconds,
        extract(hour from min(created_at))                       as start_hour,
        count(distinct headline)                                 as n_distinct_headlines,
        count(distinct eyecatcher_id)                            as n_distinct_eyecatchers,
        min(clicks)                                              as min_arm_clicks,
        max(clicks)                                              as max_arm_clicks,
        min(impressions)                                         as min_arm_impressions,
        max(impressions)                                         as max_arm_impressions
    from ranked
    group by test_id, partition

)

select
    *,
    -- Attribution scope, not validity: the package is the randomised unit, so a
    -- two-component change is still a valid choice between packages.
    (n_distinct_headlines > 1 and n_distinct_eyecatchers > 1) as attribution_limited,
    (min_arm_clicks = 0)                                      as has_zero_click_arm,
    (max_arm_clicks = 0)                                      as all_arms_zero_clicks
from rolled
