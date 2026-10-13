WITH current_customers AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY c.customer_id, c.valid_from) AS customer_key,
        c.customer_id,
        c.customer_no,
        CAST(NULL AS TEXT) AS legacy_customer_id,
        1 AS source_system_key,
        c.name,
        c.customer_type,
        c.industry,
        c.credit_limit,
        c.payment_terms_days,
        c.status,
        c.valid_from,
        c.valid_to,
        c.is_current
    FROM {{ ref('int_customer_scd2') }} c
)
SELECT * FROM current_customers
