-- Model: stg_legacy_customers
-- Target: staging.stg_legacy_customers
-- Depends on: [raw.legacy_customers]

WITH parsed AS (
    SELECT 
        _raw_id,
        _file_name,
        _row_number,
        _extracted_at,
        _run_id,
        _source,
        legacy_customer_id,
        customer_name,
        contact_email,
        phone_number,
        tax_id,
        city,
        province,
        credit_terms,
        credit_limit,
        -- Parsed tax id (hyphens and whitespace stripped)
        REPLACE(REPLACE(tax_id, '-', ''), ' ', '') AS parsed_tax_id,
        -- Parsed credit terms (extract integer days)
        CAST(TRIM(REPLACE(REPLACE(REPLACE(credit_terms, 'days', ''), 'day', ''), ' ', '')) AS INTEGER) AS parsed_credit_terms_days,
        -- Parsed credit limit (strip currency symbols and commas)
        CAST(
            TRIM(
                REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(credit_limit, '₱', ''),
                                'PHP', ''
                            ),
                            'php', ''
                        ),
                        ',', ''
                    ),
                    ' ', ''
                )
            ) AS NUMERIC
        ) AS parsed_credit_limit
    FROM {{ raw }}.legacy_customers
)
SELECT 
    _raw_id,
    _file_name,
    _row_number,
    _extracted_at,
    _run_id,
    _source,
    legacy_customer_id,
    customer_name,
    contact_email,
    phone_number,
    tax_id,
    parsed_tax_id,
    city,
    province,
    credit_terms,
    parsed_credit_terms_days,
    credit_limit,
    parsed_credit_limit,
    -- parse_error captures any parse failure while preserving raw values
    CASE 
        WHEN parsed_credit_limit IS NULL AND credit_limit IS NOT NULL AND TRIM(credit_limit) != '' THEN 'invalid_credit_limit'
        WHEN parsed_credit_terms_days IS NULL AND credit_terms IS NOT NULL AND TRIM(credit_terms) != '' THEN 'invalid_credit_terms'
        ELSE NULL
    END AS parse_error
FROM parsed;
