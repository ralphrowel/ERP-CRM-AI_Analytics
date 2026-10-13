-- Fails if allocated payment amount exceeds total payment amount
SELECT
    allocation_key,
    payment_no,
    payment_amount,
    amount_allocated
FROM {{ ref('fact_ar_allocation') }}
WHERE amount_allocated > payment_amount
