-- Model: dim_supplier
-- Target: mart.dim_supplier
-- Grain: 1 row per vendor/supplier
-- Depends on: [staging.stg_suppliers]

SELECT
    ROW_NUMBER() OVER (ORDER BY s.id) AS supplier_key,
    s.id AS supplier_id,
    s.supplier_no,
    s.name,
    s.email,
    s.payment_terms_days,
    CASE WHEN s.status = 'active' THEN 1 ELSE 0 END AS is_active
FROM {{ staging }}.stg_suppliers s;
