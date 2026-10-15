SELECT
    ROW_NUMBER() OVER (ORDER BY grl.id) AS inventory_movement_key,
    CAST(TO_CHAR(gr.receipt_date, 'YYYYMMDD') AS INTEGER) AS date_key,
    p.product_key,
    w.warehouse_key,
    grl.quantity_received AS quantity_delta,
    gr.receipt_no
FROM {{ ref('stg_goods_receipts') }} gr
JOIN {{ ref('stg_goods_receipt_lines') }} grl ON gr.id = grl.receipt_id
LEFT JOIN {{ ref('dim_product') }} p ON p.product_id = grl.product_id
LEFT JOIN {{ ref('dim_warehouse') }} w ON w.warehouse_id = gr.warehouse_id
