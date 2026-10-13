-- Fails if total debits != total credits across posted journal lines in fact_gl_journal_line
WITH trial_balance AS (
    SELECT
        ROUND(SUM(debit_amount), 2) AS total_debit,
        ROUND(SUM(credit_amount), 2) AS total_credit
    FROM {{ ref('fact_gl_journal_line') }}
    WHERE status = 'posted'
)
SELECT *
FROM trial_balance
WHERE total_debit != total_credit
