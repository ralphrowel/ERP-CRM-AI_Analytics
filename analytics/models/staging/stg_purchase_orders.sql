-- Model: stg_purchase_orders
-- Target: staging.stg_purchase_orders
-- Depends on: [raw.purchase_orders]

WITH ranked AS (
    SELECT 
        id,
        po_no,
        supplier_id,
        warehouse_id,
        status,
        order_date,
        expected_date,
        subtotal,
        tax_total,
        grand_total,
        notes,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.purchase_orders
)
SELECT 
    id,
    po_no,
    po_no AS po_number,
    supplier_id,
    warehouse_id,
    status,
    order_date,
    expected_date,
    expected_date AS expected_delivery_date,
    subtotal,
    tax_total,
    grand_total,
    grand_total AS total_amount,
    notes,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
