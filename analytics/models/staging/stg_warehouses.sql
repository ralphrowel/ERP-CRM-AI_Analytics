-- Model: stg_warehouses
-- Target: staging.stg_warehouses
-- Depends on: [raw.warehouses]

WITH ranked AS (
    SELECT 
        id,
        code,
        name,
        address,
        is_active,
        is_default,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.warehouses
)
SELECT 
    id,
    code,
    name,
    address,
    is_active,
    is_default,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
