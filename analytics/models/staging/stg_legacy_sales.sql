-- Model: stg_legacy_sales
-- Target: staging.stg_legacy_sales
-- Depends on: [raw.legacy_sales]

WITH date_extracted AS (
    SELECT 
        _raw_id,
        _file_name,
        _row_number,
        _extracted_at,
        _run_id,
        _source,
        invoice_no,
        order_date,
        legacy_customer_id,
        customer_name,
        sku,
        item_description,
        quantity,
        unit_price,
        total_amount,
        payment_status,
        -- Extract components based on format
        CASE 
            WHEN order_date LIKE '__/__/____' THEN CAST(SUBSTR(order_date, 7, 4) AS INT)
            ELSE CAST(SUBSTR(order_date, 1, 4) AS INT)
        END AS _yr,
        CASE 
            WHEN order_date LIKE '__/__/____' THEN CAST(SUBSTR(order_date, 1, 2) AS INT)
            ELSE CAST(SUBSTR(order_date, 6, 2) AS INT)
        END AS _mo,
        CASE 
            WHEN order_date LIKE '__/__/____' THEN CAST(SUBSTR(order_date, 4, 2) AS INT)
            ELSE CAST(SUBSTR(order_date, 9, 2) AS INT)
        END AS _dy,
        CASE 
            WHEN order_date LIKE '__/__/____' THEN SUBSTR(order_date, 7, 4) || '-' || SUBSTR(order_date, 1, 2) || '-' || SUBSTR(order_date, 4, 2)
            WHEN order_date LIKE '____.__.__' THEN REPLACE(order_date, '.', '-')
            ELSE order_date
        END AS _iso_date_str
    FROM {{ raw }}.legacy_sales
),
validation AS (
    SELECT 
        *,
        CASE 
            WHEN _mo BETWEEN 1 AND 12 AND _dy >= 1 AND _dy <= (
                CASE 
                    WHEN _mo IN (1, 3, 5, 7, 8, 10, 12) THEN 31
                    WHEN _mo IN (4, 6, 9, 11) THEN 30
                    WHEN _mo = 2 AND ((_yr % 4 = 0 AND _yr % 100 != 0) OR _yr % 400 = 0) THEN 29
                    ELSE 28
                END
            ) THEN 1
            ELSE 0
        END AS _is_valid_date
    FROM date_extracted
)
SELECT 
    _raw_id,
    _file_name,
    _row_number,
    _extracted_at,
    _run_id,
    _source,
    invoice_no,
    order_date,
    legacy_customer_id,
    customer_name,
    sku,
    item_description,
    quantity,
    unit_price,
    total_amount,
    payment_status,
    -- Parsed attributes
    CASE WHEN _is_valid_date = 1 THEN _iso_date_str ELSE NULL END AS parsed_order_date,
    CAST(quantity AS NUMERIC) AS parsed_quantity,
    CAST(
        TRIM(
            REPLACE(REPLACE(REPLACE(REPLACE(unit_price, '₱', ''), 'PHP', ''), ',', ''), ' ', '')
        ) AS NUMERIC
    ) AS parsed_unit_price,
    CAST(
        TRIM(
            REPLACE(REPLACE(REPLACE(REPLACE(total_amount, '₱', ''), 'PHP', ''), ',', ''), ' ', '')
        ) AS NUMERIC
    ) AS parsed_total_amount,
    -- Parse error tracking
    CASE 
        WHEN _is_valid_date = 0 AND CAST(quantity AS NUMERIC) < 0 THEN 'invalid_order_date;negative_quantity'
        WHEN _is_valid_date = 0 THEN 'invalid_order_date'
        WHEN CAST(quantity AS NUMERIC) < 0 THEN 'negative_quantity'
        ELSE NULL
    END AS parse_error
FROM validation;
