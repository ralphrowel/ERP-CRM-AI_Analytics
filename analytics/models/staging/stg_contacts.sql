-- Model: stg_contacts
-- Target: staging.stg_contacts
-- Depends on: [raw.contacts]

WITH ranked AS (
    SELECT 
        id,
        customer_id,
        first_name,
        last_name,
        email,
        phone,
        job_title,
        is_primary,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.contacts
)
SELECT 
    id,
    customer_id,
    first_name,
    last_name,
    email,
    phone,
    job_title,
    is_primary,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
