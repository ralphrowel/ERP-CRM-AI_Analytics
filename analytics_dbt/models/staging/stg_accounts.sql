WITH ranked AS (
    SELECT 
        id,
        code,
        name,
        account_type,
        normal_balance,
        description,
        parent_id,
        is_active,
        is_reconcilable,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ source('raw', 'accounts') }}
)
SELECT 
    id,
    code,
    name,
    account_type,
    normal_balance,
    description,
    parent_id,
    is_active,
    is_reconcilable,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1
