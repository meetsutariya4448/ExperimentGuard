-- Grain: one row per arm (package).
select
    p.arm_id,
    p.test_id,
    p.partition,
    p.created_at,
    p.headline,
    p.eyecatcher_id,
    p.slug,
    p.lede,
    p.excerpt,
    p.test_week,
    (p.arm_id = a.reference_arm_id) as is_reference_arm
from {{ ref('stg_packages') }} p
left join {{ ref('int_experiment_arms') }} a on a.test_id = p.test_id
