WITH raw_customers AS (
    SELECT
        id AS customer_id,
        customer_no,
        name,
        customer_type,
        status,
        industry,
        credit_limit,
        payment_terms_days,
        created_at,
        updated_at,
        _extracted_at,
        ROW_NUMBER() OVER (
            PARTITION BY id 
            ORDER BY updated_at ASC, _extracted_at ASC
        ) AS revision_no
    FROM {{ source('raw', 'customers') }}
),
with_validity AS (
    SELECT
        customer_id,
        customer_no,
        name,
        customer_type,
        status,
        industry,
        credit_limit,
        payment_terms_days,
        updated_at AS valid_from,
        LEAD(updated_at) OVER (
            PARTITION BY customer_id 
            ORDER BY updated_at ASC, _extracted_at ASC
        ) AS valid_to,
        revision_no
    FROM raw_customers
)
SELECT
    customer_id,
    customer_no,
    name,
    customer_type,
    status,
    industry,
    credit_limit,
    payment_terms_days,
    valid_from,
    valid_to,
    CASE WHEN valid_to IS NULL THEN TRUE ELSE FALSE END AS is_current
FROM with_validity
