SELECT
    ROW_NUMBER() OVER (ORDER BY s.id) AS supplier_key,
    s.id AS supplier_id,
    s.supplier_no,
    s.name,
    s.contact_name,
    s.email,
    s.phone,
    s.is_active
FROM {{ ref('stg_suppliers') }} s
