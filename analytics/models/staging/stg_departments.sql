-- Model: stg_departments
-- Target: staging.stg_departments
-- Depends on: [raw.departments]

WITH ranked AS (
    SELECT 
        id,
        code,
        name,
        is_active,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.departments
)
SELECT 
    id,
    code,
    name,
    is_active,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
