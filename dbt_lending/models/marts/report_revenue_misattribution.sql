-- Side-by-side: total loan principal per risk tier under Type 1 (naive) vs Type 2 (correct).
-- The misattribution_amount column shows how much principal is wrongly attributed
-- when using Type 1 — a direct number to present in interviews or to a risk team.

{{
    config(materialized='table')
}}

with type1_summary as (
    select
        risk_tier_current                   as risk_tier,
        sum(principal_amount)               as total_principal_type1,
        count(*)                            as loan_count_type1
    from {{ ref('fct_loans_type1') }}
    group by 1
),

type2_summary as (
    select
        risk_tier_at_origination            as risk_tier,
        sum(principal_amount)               as total_principal_type2,
        count(*)                            as loan_count_type2
    from {{ ref('fct_loans_type2') }}
    where risk_tier_at_origination is not null
    group by 1
)

select
    coalesce(t1.risk_tier, t2.risk_tier, 'Deleted / Unresolved')  as risk_tier,
    coalesce(t1.total_principal_type1, 0)   as total_principal_type1,
    coalesce(t2.total_principal_type2, 0)   as total_principal_type2,
    coalesce(t2.total_principal_type2, 0)
        - coalesce(t1.total_principal_type1, 0) as misattribution_amount,
    coalesce(t1.loan_count_type1, 0)        as loan_count_type1,
    coalesce(t2.loan_count_type2, 0)        as loan_count_type2
from type1_summary t1
full outer join type2_summary t2
    on t1.risk_tier = t2.risk_tier
order by risk_tier
