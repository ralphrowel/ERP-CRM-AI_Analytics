-- Model: dim_warehouse
-- Target: mart.dim_warehouse
-- Grain: 1 row per warehouse location
-- Depends on: [staging.stg_warehouses]

SELECT
    ROW_NUMBER() OVER (ORDER BY w.id) AS warehouse_key,
    w.id AS warehouse_id,
    w.code,
    w.name,
    CASE WHEN w.is_active THEN 1 ELSE 0 END AS is_active
FROM {{ staging }}.stg_warehouses w;
