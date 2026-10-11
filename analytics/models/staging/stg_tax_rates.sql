-- Model: stg_tax_rates
-- Target: staging.stg_tax_rates
-- Depends on: [raw.tax_rates]

WITH ranked AS (
    SELECT 
        id,
        code,
        name,
        rate,
        is_default,
        is_active,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.tax_rates
)
SELECT 
    id,
    code,
    name,
    rate,
    is_default,
    is_active,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
