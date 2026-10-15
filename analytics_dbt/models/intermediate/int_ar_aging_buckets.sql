WITH active_invoices AS (
    SELECT
        id AS invoice_id,
        invoice_no,
        customer_id,
        issue_date,
        due_date,
        grand_total,
        amount_paid,
        balance_due,
        status
    FROM {{ ref('stg_invoices') }}
    WHERE status IN ('issued', 'partially_paid')
      AND balance_due > 0
),
aging_calc AS (
    SELECT
        invoice_id,
        invoice_no,
        customer_id,
        issue_date,
        due_date,
        grand_total,
        amount_paid,
        balance_due,
        status,
        -- Days overdue calculation (relative to due date)
        CAST(CURRENT_DATE - due_date AS INTEGER) AS days_overdue
    FROM active_invoices
)
SELECT
    invoice_id,
    invoice_no,
    customer_id,
    issue_date,
    due_date,
    grand_total,
    amount_paid,
    balance_due,
    status,
    days_overdue,
    CASE
        WHEN days_overdue <= 0 THEN 'current'
        WHEN days_overdue BETWEEN 1 AND 30 THEN '1-30_days'
        WHEN days_overdue BETWEEN 31 AND 60 THEN '31-60_days'
        WHEN days_overdue BETWEEN 61 AND 90 THEN '61-90_days'
        ELSE 'over_90_days'
    END AS aging_bucket
FROM aging_calc
