-- Correct Type 2 approach: joins loans to the snapshot row valid at origination_date.
-- Each loan is attributed to whatever tier the customer held on the day the loan
-- was originated — preserving the historical record regardless of subsequent changes.

{{
    config(materialized='table')
}}

with loans as (
    select * from {{ ref('stg_loans') }}
),

-- The snapshot table: one row per customer per version.
-- dbt_valid_from / dbt_valid_to bracket the period when that tier was in effect.
-- dbt_valid_to IS NULL means the row is the current (open) version.
customer_history as (
    select * from {{ ref('dim_customers_snapshot') }}
)

select
    l.loan_id,
    l.customer_id,
    l.loan_type,
    l.principal_amount,
    l.origination_date,
    l.status,
    snap.dbt_scd_id       as customer_snapshot_key,
    snap.risk_tier        as risk_tier_at_origination,
    snap.full_name,
    snap.dbt_valid_from,
    snap.dbt_valid_to
from loans l
left join customer_history snap
    on  l.customer_id    = snap.customer_id
    and l.origination_date >= snap.dbt_valid_from::date
    and (
        l.origination_date < snap.dbt_valid_to::date
        or snap.dbt_valid_to is null
    )
