with source as (
    select * from {{ source('raw', 'loans') }}
),

renamed as (
    select
        loan_id,
        customer_id,
        loan_type,
        principal_amount,
        origination_date,
        status,
        _fivetran_synced
    from source
)

select * from renamed
