SELECT
    ROW_NUMBER() OVER (ORDER BY jl.id) AS journal_line_key,
    CAST(TO_CHAR(j.posting_date, 'YYYYMMDD') AS INTEGER) AS date_key,
    a.account_key,
    j.id AS journal_entry_id,
    j.entry_no,
    j.posting_date,
    j.fiscal_period_id,
    j.source_document_type,
    j.source_document_id,
    j.status,
    jl.line_no,
    jl.debit_amount,
    jl.credit_amount,
    (jl.debit_amount - jl.credit_amount) AS net_amount,
    jl.description AS line_description
FROM {{ ref('stg_journal_entry_lines') }} jl
JOIN {{ ref('stg_journal_entries') }} j ON j.id = jl.journal_entry_id
JOIN {{ ref('dim_account') }} a ON a.account_id = jl.account_id
