-- Model: fact_opportunity_stage
-- Target: mart.fact_opportunity_stage
-- Grain: 1 row per opportunity stage transition
-- Unique Key / Enforced Grain: (opportunity_id, transition_id)
-- Depends on: [mart.dim_date, mart.dim_customer, mart.dim_employee]

SELECT
    ROW_NUMBER() OVER (ORDER BY h.id) AS stage_fact_key,
    CAST(strftime('%Y%m%d', h.created_at) AS INTEGER) AS date_key,
    h.entity_id AS opportunity_id,
    h.id AS transition_id,
    COALESCE(c.customer_key, 0) AS customer_key,
    COALESCE(e.employee_key, 0) AS employee_key,
    h.from_status AS from_stage,
    h.to_status AS to_stage,
    CAST(COALESCE(ROUND((julianday(h.created_at) - julianday(h.previous_transition_at))), 0) AS INTEGER) AS days_in_previous_stage,
    COALESCE(o.estimated_amount, 0.0) AS estimated_amount
FROM status_history h
JOIN opportunities o ON o.id = h.entity_id AND h.entity_type = 'opportunity'
LEFT JOIN {{ mart }}.dim_customer c ON c.customer_id = o.customer_id AND c.is_current = 1
LEFT JOIN {{ mart }}.dim_employee e ON e.employee_id = h.changed_by_user_id;
