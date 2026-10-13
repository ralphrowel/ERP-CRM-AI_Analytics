SELECT
    ROW_NUMBER() OVER (ORDER BY p.id) AS product_key,
    p.id AS product_id,
    p.sku,
    p.name,
    p.uom,
    p.product_type,
    p.list_price,
    p.is_active
FROM {{ ref('stg_products') }} p
