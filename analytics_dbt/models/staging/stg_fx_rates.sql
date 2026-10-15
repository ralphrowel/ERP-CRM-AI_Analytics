WITH ranked AS (
    SELECT 
        id,
        from_currency_code,
        to_currency_code,
        effective_date,
        rate,
        source,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ source('raw', 'fx_rates') }}
)
SELECT 
    id,
    from_currency_code,
    to_currency_code,
    effective_date,
    rate,
    source,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1
