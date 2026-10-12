-- Model: fact_sales_line
-- Target: mart.fact_sales_line
-- Grain: 1 row per invoice line, credit-note line (negative revenue), or legacy sale item
-- Unique Key / Enforced Grain: (source_system_key, document_type, COALESCE(invoice_no, credit_note_no), line_number)
-- Depends on: [mart.dim_date, mart.dim_customer, mart.dim_product, mart.dim_employee, mart.dim_source_system, staging.stg_invoices, staging.stg_invoice_lines]

WITH erp_invoices AS (
    SELECT
        CAST(strftime('%Y%m%d', i.issue_date) AS INTEGER) AS date_key,
        c.customer_key,
        p.product_key,
        COALESCE(e.employee_key, 0) AS employee_key,
        1 AS source_system_key,
        i.invoice_no,
        CAST(NULL AS TEXT) AS credit_note_no,
        'invoice' AS document_type,
        'erp' AS source_system,
        il.line_number,
        il.quantity,
        il.unit_price,
        il.subtotal AS gross,
        il.discount_amount AS discount,
        il.subtotal AS net_revenue,
        il.tax_amount AS tax,
        (il.quantity * COALESCE(p.standard_cost, 0)) AS cogs,
        (il.subtotal - (il.quantity * COALESCE(p.standard_cost, 0))) AS gross_margin
    FROM {{ staging }}.stg_invoices i
    JOIN {{ staging }}.stg_invoice_lines il ON i.id = il.invoice_id
    -- Effective dating join into dim_customer (SCD Type 2)
    JOIN {{ mart }}.dim_customer c ON c.customer_id = i.customer_id
        AND i.issue_date >= c.valid_from
        AND (c.valid_to IS NULL OR i.issue_date < c.valid_to)
    LEFT JOIN {{ mart }}.dim_product p ON p.product_id = il.product_id
    LEFT JOIN {{ mart }}.dim_employee e ON e.employee_id = i.created_by_user_id
    WHERE i.status IN ('issued', 'partially_paid', 'paid')
),
erp_credit_notes AS (
    SELECT
        CAST(strftime('%Y%m%d', cn.issue_date) AS INTEGER) AS date_key,
        c.customer_key,
        p.product_key,
        COALESCE(e.employee_key, 0) AS employee_key,
        1 AS source_system_key,
        CAST(NULL AS TEXT) AS invoice_no,
        cn.credit_note_no,
        'credit_note' AS document_type,
        'erp' AS source_system,
        cnl.line_number,
        -cnl.quantity AS quantity,
        cnl.unit_price,
        -cnl.subtotal AS gross,
        0.0 AS discount,
        -cnl.subtotal AS net_revenue,
        -cnl.tax_amount AS tax,
        -(cnl.quantity * COALESCE(p.standard_cost, 0)) AS cogs,
        -(cnl.subtotal - (cnl.quantity * COALESCE(p.standard_cost, 0))) AS gross_margin
    FROM {{ staging }}.stg_credit_notes cn
    JOIN {{ staging }}.stg_credit_note_lines cnl ON cn.id = cnl.credit_note_id
    JOIN {{ mart }}.dim_customer c ON c.customer_id = cn.customer_id
        AND cn.issue_date >= c.valid_from
        AND (c.valid_to IS NULL OR cn.issue_date < c.valid_to)
    LEFT JOIN {{ mart }}.dim_product p ON p.product_id = cnl.product_id
    LEFT JOIN {{ mart }}.dim_employee e ON e.employee_id = cn.created_by_user_id
    WHERE cn.status = 'issued'
),
legacy_sales AS (
    SELECT
        CAST(strftime('%Y%m%d', ls.sale_date) AS INTEGER) AS date_key,
        c.customer_key,
        p.product_key,
        0 AS employee_key,
        2 AS source_system_key,
        ls.legacy_sale_id AS invoice_no,
        CAST(NULL AS TEXT) AS credit_note_no,
        'legacy_sale' AS document_type,
        'legacy' AS source_system,
        1 AS line_number,
        ls.quantity,
        ls.unit_price,
        ls.subtotal AS gross,
        0.0 AS discount,
        ls.subtotal AS net_revenue,
        ls.tax_amount AS tax,
        (ls.quantity * COALESCE(p.standard_cost, 0)) AS cogs,
        (ls.subtotal - (ls.quantity * COALESCE(p.standard_cost, 0))) AS gross_margin
    FROM {{ staging }}.stg_legacy_sales ls
    JOIN {{ mart }}.dim_customer c ON c.legacy_customer_id = ls.legacy_customer_id
    LEFT JOIN {{ mart }}.dim_product p ON p.sku = ls.product_sku
)
SELECT * FROM erp_invoices
UNION ALL
SELECT * FROM erp_credit_notes
UNION ALL
SELECT * FROM legacy_sales;
