with source as (
    select * from {{ source('raw', 'customers') }}
),

renamed as (
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
    from source
    where _fivetran_deleted = false
)

select * from renamed
