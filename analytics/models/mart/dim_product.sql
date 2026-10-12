-- Model: dim_product
-- Target: mart.dim_product
-- Grain: 1 row per conformed product
-- Depends on: [staging.stg_products]

SELECT
    ROW_NUMBER() OVER (ORDER BY p.id) AS product_key,
    p.id AS product_id,
    p.sku,
    p.name,
    p.category,
    p.unit_of_measure,
    p.standard_cost,
    p.list_price,
    CASE WHEN p.status = 'active' THEN 1 ELSE 0 END AS is_active
FROM {{ staging }}.stg_products p;
