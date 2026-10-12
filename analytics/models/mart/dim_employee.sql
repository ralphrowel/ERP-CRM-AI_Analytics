-- Model: dim_employee
-- Target: mart.dim_employee
-- Grain: 1 row per employee
-- Depends on: []

SELECT
    ROW_NUMBER() OVER (ORDER BY u.id) AS employee_key,
    u.id AS employee_id,
    'EMP-' || CAST(u.id AS TEXT) AS employee_no,
    COALESCE(u.full_name, u.username) AS full_name,
    u.email,
    d.code AS department_code,
    d.name AS department_name,
    u.role,
    CASE WHEN u.is_active THEN 1 ELSE 0 END AS is_active
FROM users u
LEFT JOIN {{ staging }}.stg_departments d ON u.department_id = d.id;
