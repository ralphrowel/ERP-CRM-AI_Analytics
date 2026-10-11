-- Model: stg_products
-- Target: staging.stg_products
-- Depends on: [raw.products]

WITH ranked AS (
    SELECT 
        id,
        sku,
        name,
        description,
        category_id,
        product_type,
        uom,
        list_price,
        is_active,
        reorder_point,
        tax_rate_id,
        created_at,
        updated_at,
        _extracted_at,
        _run_id,
        _source,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY _extracted_at DESC, _raw_id DESC) AS _rn
    FROM {{ raw }}.products
)
SELECT 
    id,
    sku,
    name,
    description,
    category_id,
    product_type,
    uom,
    list_price,
    is_active,
    reorder_point,
    tax_rate_id,
    created_at,
    updated_at,
    _extracted_at,
    _run_id,
    _source
FROM ranked
WHERE _rn = 1;
