-- Model: fact_purchase_line
-- Target: mart.fact_purchase_line
-- Grain: 1 row per purchase order line
-- Unique Key / Enforced Grain: (po_no, line_number)
-- Depends on: [mart.dim_date, mart.dim_supplier, mart.dim_product, staging.stg_purchase_orders, staging.stg_purchase_order_lines]

SELECT
    ROW_NUMBER() OVER (ORDER BY po.po_no, pol.line_number) AS purchase_fact_key,
    CAST(strftime('%Y%m%d', po.order_date) AS INTEGER) AS date_key,
    COALESCE(s.supplier_key, 0) AS supplier_key,
    COALESCE(p.product_key, 0) AS product_key,
    po.po_no,
    pol.line_number,
    pol.quantity AS qty_ordered,
    COALESCE(pol.quantity_received, 0) AS qty_received,
    pol.unit_cost,
    pol.subtotal AS cost,
    CASE
        WHEN gr.receipt_date IS NOT NULL AND po.expected_delivery_date IS NOT NULL
        THEN CAST(MAX(0, ROUND(julianday(gr.receipt_date) - julianday(po.expected_delivery_date))) AS INTEGER)
        ELSE 0
    END AS days_late
FROM {{ staging }}.stg_purchase_orders po
JOIN {{ staging }}.stg_purchase_order_lines pol ON po.id = pol.purchase_order_id
LEFT JOIN {{ mart }}.dim_supplier s ON s.supplier_id = po.supplier_id
LEFT JOIN {{ mart }}.dim_product p ON p.product_id = pol.product_id
LEFT JOIN {{ staging }}.stg_goods_receipts gr ON gr.purchase_order_id = po.id;
