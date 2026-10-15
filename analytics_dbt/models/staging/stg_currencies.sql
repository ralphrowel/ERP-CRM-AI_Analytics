WITH ranked AS (
    SELECT 
        code,
        name,
        symbol,
        decimal_places,
        is_base,
        is_active,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY code ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ source('raw', 'currencies') }}
)
SELECT 
    code,
    name,
    symbol,
    decimal_places,
    is_base,
    is_active,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1
