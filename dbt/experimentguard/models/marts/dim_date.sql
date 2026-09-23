-- Grain: one row per calendar date on which an experiment started.
--
-- Carries the documented cache-misconfiguration window so any date-sliced view can
-- show reliable and unreliable periods side by side.
with days as (

    select distinct cast(started_at as date) as date_day
    from {{ ref('int_experiment_arms') }}

)

select
    date_day,
    extract(year from date_day)     as year,
    extract(month from date_day)    as month,
    extract(day from date_day)      as day_of_month,
    extract(dow from date_day)      as day_of_week,
    date_trunc('week', date_day)    as week_start,
    date_trunc('month', date_day)   as month_start,
    (date_day between date '2013-06-25' and date '2014-01-10')
        as in_cache_misconfiguration_window
from days
