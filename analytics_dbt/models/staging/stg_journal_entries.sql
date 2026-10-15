WITH ranked AS (
    SELECT 
        id,
        entry_no,
        posting_date,
        fiscal_period_id,
        source_document_type,
        source_document_id,
        status,
        total_debit,
        total_credit,
        description,
        reversal_of_id,
        posted_at,
        posted_by,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ source('raw', 'journal_entries') }}
)
SELECT 
    id,
    entry_no,
    posting_date,
    fiscal_period_id,
    source_document_type,
    source_document_id,
    status,
    total_debit,
    total_credit,
    description,
    reversal_of_id,
    posted_at,
    posted_by,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1
