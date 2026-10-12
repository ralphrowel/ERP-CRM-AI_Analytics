-- Model: dim_date
-- Target: mart.dim_date
-- Grain: 1 row per calendar day (Asia/Manila, 2023-2026)
-- Depends on: []

SELECT
    CAST(strftime('%Y%m%d', d) AS INTEGER) AS date_key,
    d AS full_date,
    CAST(strftime('%Y', d) AS INTEGER) AS year,
    CAST(strftime('%m', d) AS INTEGER) AS month,
    CAST(strftime('%d', d) AS INTEGER) AS day,
    -- Calendar = Fiscal (Asia/Manila)
    CAST(strftime('%Y', d) AS INTEGER) AS fiscal_year,
    (CAST(strftime('%m', d) AS INTEGER) - 1) / 3 + 1 AS fiscal_quarter,
    CAST(strftime('%m', d) AS INTEGER) AS fiscal_month,
    (CAST(strftime('%m', d) AS INTEGER) - 1) / 3 + 1 AS calendar_quarter,
    -- Day of week: 0=Sunday, 6=Saturday in strftime('%w', ...)
    CAST(strftime('%w', d) AS INTEGER) AS day_of_week,
    CASE CAST(strftime('%w', d) AS INTEGER)
        WHEN 0 THEN 'Sunday'
        WHEN 1 THEN 'Monday'
        WHEN 2 THEN 'Tuesday'
        WHEN 3 THEN 'Wednesday'
        WHEN 4 THEN 'Thursday'
        WHEN 5 THEN 'Friday'
        ELSE 'Saturday'
    END AS day_name,
    CASE CAST(strftime('%m', d) AS INTEGER)
        WHEN 1 THEN 'January'
        WHEN 2 THEN 'February'
        WHEN 3 THEN 'March'
        WHEN 4 THEN 'April'
        WHEN 5 THEN 'May'
        WHEN 6 THEN 'June'
        WHEN 7 THEN 'July'
        WHEN 8 THEN 'August'
        WHEN 9 THEN 'September'
        WHEN 10 THEN 'October'
        WHEN 11 THEN 'November'
        ELSE 'December'
    END AS month_name,
    CASE CAST(strftime('%w', d) AS INTEGER)
        WHEN 0 THEN 1
        WHEN 6 THEN 1
        ELSE 0
    END AS is_weekend
FROM calendar_generator;
