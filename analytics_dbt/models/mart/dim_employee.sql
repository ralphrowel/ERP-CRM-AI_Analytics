SELECT
    ROW_NUMBER() OVER (ORDER BY d.id) AS employee_key,
    d.id AS employee_id,
    d.code AS department_code,
    d.name AS department_name
FROM {{ ref('stg_departments') }} d
