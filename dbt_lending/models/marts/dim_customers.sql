-- Current-state customer dimension: one row per active customer.
-- Hard-deleted customers are excluded automatically — invalidate_hard_deletes
-- closes their snapshot rows, so they never appear here.

select
    customer_id,
    full_name,
    email,
    city,
    risk_tier,
    member_since,
    updated_at,
    dbt_valid_from  as valid_from
from {{ ref('dim_customers_snapshot') }}
where dbt_valid_to is null
