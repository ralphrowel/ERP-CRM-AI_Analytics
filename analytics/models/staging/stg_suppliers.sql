-- Model: stg_suppliers
-- Target: staging.stg_suppliers
-- Depends on: [raw.suppliers]

WITH ranked AS (
    SELECT 
        id,
        supplier_no,
        supplier_no AS supplier_code,
        name,
        tin AS tax_id,
        email,
        phone,
        address,
        payment_terms_days,
        is_active,
        CASE WHEN is_active THEN 'active' ELSE 'inactive' END AS status,
        notes,
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
    supplier_no,
    supplier_code,
    name,
    tax_id,
    email,
    phone,
    address,
    payment_terms_days,
    is_active,
    status,
    notes,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
