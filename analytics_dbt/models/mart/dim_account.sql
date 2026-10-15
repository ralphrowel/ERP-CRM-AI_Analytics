SELECT
    ROW_NUMBER() OVER (ORDER BY a.code) AS account_key,
    a.id AS account_id,
    a.code AS account_code,
    a.name AS account_name,
    a.account_type,
    a.normal_balance,
    a.description,
    a.is_reconcilable,
    a.is_active
FROM {{ ref('stg_accounts') }} a
