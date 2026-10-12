-- Model: stg_purchase_order_lines
-- Target: staging.stg_purchase_order_lines
-- Depends on: [raw.purchase_order_items]

WITH ranked AS (
    SELECT 
        id,
        purchase_order_id,
        line_no,
        product_id,
        description,
        uom,
        quantity,
        unit_cost,
        tax_rate_id,
        tax_rate,
        line_net,
        line_tax,
        line_total,
        quantity_received,
        quantity_billed,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.purchase_order_items
)
SELECT 
    id,
    purchase_order_id,
    line_no,
    line_no AS line_number,
    product_id,
    description,
    uom,
    quantity,
    quantity AS quantity_ordered,
    unit_cost,
    ROUND(quantity * unit_cost, 4) AS line_subtotal,
    tax_rate_id,
    tax_rate,
    line_net,
    line_net AS subtotal,
    line_tax,
    line_total,
    quantity_received,
    quantity_billed,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
