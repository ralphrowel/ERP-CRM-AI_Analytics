WITH erp_invoices AS (
    SELECT
        CAST(TO_CHAR(i.issue_date, 'YYYYMMDD') AS INTEGER) AS date_key,
        c.customer_key,
        p.product_key,
        1 AS source_system_key,
        i.invoice_no,
        'invoice' AS document_type,
        il.line_number,
        il.quantity,
        il.unit_price,
        il.subtotal AS gross,
        il.discount_amount AS discount,
        il.subtotal AS net_revenue,
        il.tax_amount AS tax
    FROM {{ ref('stg_invoices') }} i
    JOIN {{ ref('stg_invoice_lines') }} il ON i.id = il.invoice_id
    JOIN {{ ref('dim_customer') }} c ON c.customer_id = i.customer_id AND c.is_current = TRUE
    LEFT JOIN {{ ref('dim_product') }} p ON p.product_id = il.product_id
    WHERE i.status IN ('issued', 'partially_paid', 'paid')
)
SELECT 
    ROW_NUMBER() OVER (ORDER BY invoice_no, line_number) AS sales_line_key,
    *
FROM erp_invoices
