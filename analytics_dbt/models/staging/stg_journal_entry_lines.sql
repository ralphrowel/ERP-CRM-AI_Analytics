WITH ranked AS (
    SELECT 
        id,
        journal_entry_id,
        line_no,
        account_id,
        debit_amount,
        credit_amount,
        description,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ source('raw', 'journal_entry_lines') }}
)
SELECT 
    id,
    journal_entry_id,
    line_no,
    account_id,
    debit_amount,
    credit_amount,
    description,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1
