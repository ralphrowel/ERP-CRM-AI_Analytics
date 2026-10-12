-- Model: fact_ar_allocation
-- Target: mart.fact_ar_allocation
-- Grain: 1 row per payment allocation
-- Unique Key / Enforced Grain: (payment_no, allocation_id)
-- Depends on: [mart.dim_date, mart.dim_customer, staging.stg_payments, staging.stg_invoices]

SELECT
    ROW_NUMBER() OVER (ORDER BY p.payment_no, pa.id) AS ar_fact_key,
    CAST(strftime('%Y%m%d', p.payment_date) AS INTEGER) AS date_key,
    COALESCE(c.customer_key, 0) AS customer_key,
    p.payment_no,
    pa.id AS allocation_id,
    i.invoice_no,
    pa.amount,
    CASE
        WHEN i.due_date IS NOT NULL
        THEN CAST(ROUND(julianday(p.payment_date) - julianday(i.due_date)) AS INTEGER)
        ELSE 0
    END AS days_after_due
FROM {{ staging }}.stg_payments p
JOIN payment_allocations pa ON pa.payment_id = p.id
JOIN {{ staging }}.stg_invoices i ON i.id = pa.invoice_id
LEFT JOIN {{ mart }}.dim_customer c ON c.customer_id = p.customer_id
    AND p.payment_date >= c.valid_from
    AND (c.valid_to IS NULL OR p.payment_date < c.valid_to);
