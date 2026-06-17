-- Naive Type 1 approach: joins loans to the customer's CURRENT risk tier.
-- Problem: if a customer was High-Risk at origination but is Standard today,
-- their loan's principal gets attributed to Standard tier — understating
-- the portfolio's historical risk exposure.

{{
    config(materialized='table')
}}

with loans as (
    select * from {{ ref('stg_loans') }}
),

customers_current as (
    select * from {{ ref('dim_customers') }}
)

select
    l.loan_id,
    l.customer_id,
    l.loan_type,
    l.principal_amount,
    l.origination_date,
    l.status,
    c.risk_tier           as risk_tier_current,
    c.full_name
from loans l
left join customers_current c
    on l.customer_id = c.customer_id
