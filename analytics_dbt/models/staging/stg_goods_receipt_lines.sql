WITH ranked AS (
    SELECT 
        id,
        goods_receipt_id,
        purchase_order_item_id,
        product_id,
        quantity,
        unit_cost,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ source('raw', 'goods_receipt_items') }}
)
SELECT 
    id,
    goods_receipt_id,
    purchase_order_item_id,
    product_id,
    quantity,
    unit_cost,
    ROUND(quantity * unit_cost, 4) AS line_total,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
