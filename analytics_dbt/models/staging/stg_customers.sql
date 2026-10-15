WITH ranked AS (
    SELECT 
        id,
        customer_no,
        name,
        customer_type,
        status,
        tin,
        email,
        phone,
        website,
        industry,
        payment_terms_days,
        credit_limit,
        owner_user_id,
        notes,
        version,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ source('raw', 'customers') }}
)
SELECT 
    id,
    customer_no,
    name,
    customer_type,
    status,
    tin,
    email,
    phone,
    website,
    industry,
    payment_terms_days,
    credit_limit,
    owner_user_id,
    notes,
    version,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
