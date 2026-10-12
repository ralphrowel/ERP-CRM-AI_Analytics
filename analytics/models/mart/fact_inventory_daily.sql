-- Model: fact_inventory_daily
-- Target: mart.fact_inventory_daily
-- Grain: 1 row per product x warehouse x day snapshot
-- Unique Key / Enforced Grain: (date_key, product_key, warehouse_key)
-- Depends on: [mart.dim_date, mart.dim_product, mart.dim_warehouse, staging.stg_products, staging.stg_warehouses]

SELECT
    ROW_NUMBER() OVER (ORDER BY d.date_key, p.product_key, w.warehouse_key) AS inventory_fact_key,
    d.date_key,
    p.product_key,
    w.warehouse_key,
    COALESCE(i.quantity_on_hand, 0) AS qty_on_hand,
    COALESCE(i.quantity_reserved, 0) AS qty_reserved,
    COALESCE(i.quantity_on_hand * COALESCE(p.standard_cost, 0), 0.0) AS inventory_value
FROM {{ mart }}.dim_date d
CROSS JOIN {{ mart }}.dim_product p
CROSS JOIN {{ mart }}.dim_warehouse w
LEFT JOIN inventory_levels i ON i.product_id = p.product_id AND i.warehouse_id = w.warehouse_id;
