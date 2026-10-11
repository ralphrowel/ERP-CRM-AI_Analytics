-- Model: stg_sales_order_lines
-- Target: staging.stg_sales_order_lines
-- Depends on: [raw.sales_order_items]

WITH ranked AS (
    SELECT 
        id,
        sales_order_id,
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
        quantity_invoiced,
        quantity_shipped,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.sales_order_items
)
SELECT 
    id,
    sales_order_id,
    line_no,
    line_no AS line_number,
    product_id,
    description,
    uom,
    quantity,
    unit_price,
    discount_amount,
    -- Derived metrics (Roadmap §V1.2)
    ROUND(quantity * unit_price - COALESCE(discount_amount, 0), 4) AS line_subtotal,
    ROUND(line_net, 4) AS line_margin,
    tax_rate_id,
    tax_rate,
    line_net,
    line_tax,
    line_total,
    quantity_invoiced,
    quantity_shipped,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
