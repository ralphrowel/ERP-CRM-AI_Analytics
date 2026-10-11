-- Model: stg_goods_receipts
-- Target: staging.stg_goods_receipts
-- Depends on: [raw.goods_receipts]

WITH ranked AS (
    SELECT 
        id,
        gr_no,
        purchase_order_id,
        warehouse_id,
        status,
        received_at,
        supplier_delivery_ref,
        notes,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.goods_receipts
)
SELECT 
    id,
    gr_no,
    purchase_order_id,
    warehouse_id,
    status,
    received_at,
    supplier_delivery_ref,
    notes,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
