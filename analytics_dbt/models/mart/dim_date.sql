WITH RECURSIVE dates AS (
    SELECT CAST('2023-01-01' AS DATE) AS full_date
    UNION ALL
    SELECT CAST(full_date + INTERVAL '1 day' AS DATE)
    FROM dates
    WHERE full_date < CAST('2026-12-31' AS DATE)
)
SELECT
    CAST(TO_CHAR(full_date, 'YYYYMMDD') AS INTEGER) AS date_key,
    full_date,
    CAST(EXTRACT(YEAR FROM full_date) AS INTEGER) AS year,
    CAST(EXTRACT(MONTH FROM full_date) AS INTEGER) AS month,
    CAST(EXTRACT(DAY FROM full_date) AS INTEGER) AS day,
    CAST(EXTRACT(YEAR FROM full_date) AS INTEGER) AS fiscal_year,
    CAST(EXTRACT(QUARTER FROM full_date) AS INTEGER) AS fiscal_quarter,
    CAST(EXTRACT(MONTH FROM full_date) AS INTEGER) AS fiscal_month,
    CAST(EXTRACT(QUARTER FROM full_date) AS INTEGER) AS calendar_quarter,
    CAST(EXTRACT(DOW FROM full_date) AS INTEGER) AS day_of_week,
    TRIM(TO_CHAR(full_date, 'Day')) AS day_name,
    TRIM(TO_CHAR(full_date, 'Month')) AS month_name,
    CASE WHEN EXTRACT(DOW FROM full_date) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend
FROM dates
