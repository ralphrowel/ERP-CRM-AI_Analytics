-- Model: stg_suppliers
-- Target: staging.stg_suppliers
-- Depends on: [raw.suppliers]

WITH ranked AS (
    SELECT 
        id,
        supplier_code,
        name,
        contact_person,
        email,
        phone,
        tax_id,
        payment_terms_days,
        currency,
        status,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.suppliers
)
SELECT 
    id,
    supplier_code,
    name,
    contact_person,
    email,
    phone,
    tax_id,
    payment_terms_days,
    currency,
    status,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
