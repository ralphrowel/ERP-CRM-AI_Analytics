SELECT
    ROW_NUMBER() OVER (ORDER BY w.id) AS warehouse_key,
    w.id AS warehouse_id,
    w.code AS warehouse_code,
    w.name,
    w.is_active
FROM {{ ref('stg_warehouses') }} w
