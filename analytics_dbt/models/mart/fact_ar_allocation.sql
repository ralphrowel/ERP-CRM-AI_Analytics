SELECT
    ROW_NUMBER() OVER (ORDER BY p.id) AS allocation_key,
    CAST(TO_CHAR(p.payment_date, 'YYYYMMDD') AS INTEGER) AS date_key,
    c.customer_key,
    p.id AS payment_id,
    p.payment_no,
    p.amount AS payment_amount,
    p.amount_allocated,
    p.method AS payment_method,
    p.status AS payment_status
FROM {{ ref('stg_payments') }} p
JOIN {{ ref('dim_customer') }} c ON c.customer_id = p.customer_id AND c.is_current = TRUE
