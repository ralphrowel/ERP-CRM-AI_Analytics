-- Model: dim_source_system
-- Target: mart.dim_source_system
-- Grain: 1 row per upstream source system
-- Depends on: []

SELECT 1 AS source_system_key, 'erp' AS source_name, 'Modern ERP System' AS description, 1 AS is_active
UNION ALL
SELECT 2 AS source_system_key, 'legacy' AS source_name, 'Legacy Sales Database' AS description, 1 AS is_active;
