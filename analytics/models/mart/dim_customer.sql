-- Model: dim_customer
-- Target: mart.dim_customer
-- Grain: 1 row per customer revision (SCD Type 2)
-- Depends on: [staging.stg_customers, staging.stg_legacy_customers]

SELECT
    ROW_NUMBER() OVER (ORDER BY c.customer_id, c.valid_from) AS customer_key,
    c.customer_id,
    c.customer_no,
    c.legacy_customer_id,
    c.source_system_key,
    c.name,
    c.customer_type,
    c.industry,
    c.city,
    c.province,
    c.region,
    c.credit_limit,
    c.payment_terms_days,
    c.is_active,
    c.valid_from,
    c.valid_to,
    c.is_current
FROM customer_scd2_revisions c;
