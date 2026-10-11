-- Model: stg_payments
-- Target: staging.stg_payments
-- Depends on: [raw.payments]

WITH ranked AS (
    SELECT 
        id,
        payment_no,
        customer_id,
        payment_date,
        payment_method,
        amount,
        reference_no,
        status,
        notes,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.payments
)
SELECT 
    id,
    payment_no,
    customer_id,
    payment_date,
    payment_method,
    amount,
    reference_no,
    status,
    notes,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
