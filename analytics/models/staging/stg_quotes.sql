-- Model: stg_quotes
-- Target: staging.stg_quotes
-- Depends on: [raw.quotes]

WITH ranked AS (
    SELECT 
        id,
        quote_no,
        opportunity_id,
        customer_id,
        status,
        version,
        quote_date,
        valid_until,
        valid_until AS expiration_date,
        currency_code,
        currency_code AS currency,
        subtotal,
        discount_total,
        tax_total,
        grand_total,
        grand_total AS total_amount,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.quotes
)
SELECT 
    id,
    quote_no,
    opportunity_id,
    customer_id,
    status,
    version,
    quote_date,
    valid_until,
    expiration_date,
    currency,
    currency_code,
    subtotal,
    discount_total,
    tax_total,
    grand_total,
    total_amount,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
