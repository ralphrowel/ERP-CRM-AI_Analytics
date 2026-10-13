WITH ranked AS (
    SELECT 
        id,
        period_name,
        start_date,
        end_date,
        status,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ source('raw', 'fiscal_periods') }}
)
SELECT 
    id,
    period_name,
    start_date,
    end_date,
    status,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1
