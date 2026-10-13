WITH ranked AS (
    SELECT 
        id,
        payment_no,
        customer_id,
        payment_date,
        method,
        method AS payment_method,
        amount,
        amount_allocated,
        reference_no,
        status,
        void_reason AS notes,
        CAST(NULL AS INTEGER) AS invoice_id,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ source('raw', 'payments') }}
)
SELECT 
    id,
    payment_no,
    customer_id,
    payment_date,
    method,
    payment_method,
    amount,
    amount_allocated,
    reference_no,
    status,
    notes,
    invoice_id,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
