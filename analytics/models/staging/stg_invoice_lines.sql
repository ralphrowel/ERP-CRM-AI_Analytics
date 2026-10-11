-- Model: stg_invoice_lines
-- Target: staging.stg_invoice_lines
-- Depends on: [raw.invoice_items]

WITH ranked AS (
    SELECT 
        id,
        invoice_id,
        sales_order_item_id,
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
    FROM {{ raw }}.invoice_items
)
SELECT 
    id,
    invoice_id,
    sales_order_item_id,
    sales_order_item_id AS sales_order_line_id,
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
