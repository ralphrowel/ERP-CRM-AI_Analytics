-- Model: stg_quote_lines
-- Target: staging.stg_quote_lines
-- Depends on: [raw.quote_items]

WITH ranked AS (
    SELECT 
        id,
        quote_id,
        line_no,
        product_id,
        description,
        uom,
        quantity,
        unit_price,
        discount_amount,
        tax_rate_id,
        tax_rate,
        line_net,
        line_tax,
        line_total,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.quote_items
)
SELECT 
    id,
    quote_id,
    line_no,
    line_no AS line_number,
    product_id,
    description,
    uom,
    quantity,
    unit_price,
    discount_amount,
    ROUND(quantity * unit_price - COALESCE(discount_amount, 0), 4) AS line_subtotal,
    tax_rate_id,
    tax_rate,
    line_net,
    line_tax,
    line_total,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
