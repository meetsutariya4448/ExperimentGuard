-- One row per package (arm). Types normalised, HTML stripped, partitions tagged.
--
-- The deduplication guard is deliberate: arm_id is a hash of
-- (source_file, source_row_number, test_id), so a duplicate here would mean the same
-- source row was ingested twice rather than a genuine repeated measurement.

with source as (

    select * from {{ source('raw', 'raw_packages') }}

),

cleaned as (

    select
        arm_id,
        test_id,
        partition,
        source_file,
        source_row_number,
        created_at,
        cast(impressions as bigint)                          as impressions,
        cast(clicks as bigint)                               as clicks,
        clicks / nullif(impressions, 0)                      as ctr,
        headline,
        eyecatcher_id,
        slug,
        -- lede arrives wrapped in HTML paragraph tags
        trim(regexp_replace(coalesce(lede, ''), '<[^>]*>', '', 'g')) as lede,
        excerpt,
        test_week,
        first_place,
        winner,
        significance
    from source

)

select *
from cleaned
qualify row_number() over (partition by arm_id order by source_row_number) = 1
