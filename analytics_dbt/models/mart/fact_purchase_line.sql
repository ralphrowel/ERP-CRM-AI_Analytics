SELECT
    ROW_NUMBER() OVER (ORDER BY pol.id) AS purchase_line_key,
    CAST(TO_CHAR(po.order_date, 'YYYYMMDD') AS INTEGER) AS date_key,
    s.supplier_key,
    p.product_key,
    po.po_no,
    pol.line_number,
    pol.quantity,
    pol.unit_price,
    pol.subtotal,
    po.status
FROM {{ ref('stg_purchase_orders') }} po
JOIN {{ ref('stg_purchase_order_lines') }} pol ON po.id = pol.purchase_order_id
JOIN {{ ref('dim_supplier') }} s ON s.supplier_id = po.supplier_id
LEFT JOIN {{ ref('dim_product') }} p ON p.product_id = pol.product_id
