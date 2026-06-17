{% snapshot dim_customers_snapshot %}

{{
    config(
        target_schema='snapshots',
        strategy='timestamp',
        unique_key='customer_id',
        updated_at='updated_at',
        invalidate_hard_deletes=True,
    )
}}

select
    customer_id,
    full_name,
    email,
    city,
    risk_tier,
    member_since,
    updated_at,
    _fivetran_synced,
    _fivetran_deleted
from {{ source('raw', 'customers') }}

{% endsnapshot %}
