SELECT
    ROW_NUMBER() OVER (ORDER BY q.id) AS opportunity_key,
    CAST(TO_CHAR(q.issue_date, 'YYYYMMDD') AS INTEGER) AS date_key,
    c.customer_key,
    q.quote_no,
    q.status,
    q.grand_total AS pipeline_amount
FROM {{ ref('stg_quotes') }} q
JOIN {{ ref('dim_customer') }} c ON c.customer_id = q.customer_id AND c.is_current = TRUE
