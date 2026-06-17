-- Full SCD Type 2 customer history: one row per customer per version.
-- Use dbt_skey (customer_snapshot_key) to join from fact tables when you need
-- the attribute values that were in effect at a specific point in time.
-- dbt_valid_to IS NULL = current version.

select
    dbt_scd_id      as customer_snapshot_key,
    customer_id,
    full_name,
    email,
    city,
    risk_tier,
    member_since,
    updated_at,
    dbt_valid_from,
    dbt_valid_to
from {{ ref('dim_customers_snapshot') }}
