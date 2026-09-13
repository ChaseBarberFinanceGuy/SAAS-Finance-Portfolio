-- ============================================================
-- 02_data_quality.sql
-- SAAS Finance Portolio
-- Core data-quality and financial-integrity controls
-- ============================================================

CREATE OR REPLACE VIEW vw_data_quality_checks AS

-- ------------------------------------------------------------
-- 1. CUSTOMER-MONTH GRAIN
-- Expected: one row per customer_id / period_month
-- ------------------------------------------------------------
SELECT
    'subscription_month_customer_period_unique' AS check_name,
    CASE
        WHEN COUNT(*) =
             COUNT(DISTINCT customer_id || '|' || period_month)
        THEN 'PASS'
        ELSE 'FAIL'
    END AS status,
    CAST(COUNT(*) AS VARCHAR) AS observed_value,
    CAST(
        COUNT(DISTINCT customer_id || '|' || period_month)
        AS VARCHAR
    ) AS expected_or_comparison
FROM stg_subscription_months

UNION ALL

-- ------------------------------------------------------------
-- 2. CUSTOMER FOREIGN KEYS
-- ------------------------------------------------------------
SELECT
    'subscription_month_customer_fk_valid',
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
    CAST(COUNT(*) AS VARCHAR),
    '0 orphan rows'
FROM stg_subscription_months sm
LEFT JOIN stg_customers c
    ON sm.customer_id = c.customer_id
WHERE c.customer_id IS NULL

UNION ALL

-- ------------------------------------------------------------
-- 3. SUBSCRIPTION FOREIGN KEYS
-- ------------------------------------------------------------
SELECT
    'subscription_month_subscription_fk_valid',
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
    CAST(COUNT(*) AS VARCHAR),
    '0 orphan rows'
FROM stg_subscription_months sm
LEFT JOIN stg_subscriptions s
    ON sm.subscription_id = s.subscription_id
WHERE s.subscription_id IS NULL

UNION ALL

-- ------------------------------------------------------------
-- 4. PLAN FOREIGN KEYS
-- ------------------------------------------------------------
SELECT
    'subscription_month_plan_fk_valid',
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
    CAST(COUNT(*) AS VARCHAR),
    '0 orphan rows'
FROM stg_subscription_months sm
LEFT JOIN stg_plans p
    ON sm.plan_id = p.plan_id
WHERE p.plan_id IS NULL

UNION ALL

-- ------------------------------------------------------------
-- 5. INVOICE CUSTOMER FOREIGN KEYS
-- ------------------------------------------------------------
SELECT
    'invoice_customer_fk_valid',
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
    CAST(COUNT(*) AS VARCHAR),
    '0 orphan rows'
FROM stg_invoices i
LEFT JOIN stg_customers c
    ON i.customer_id = c.customer_id
WHERE c.customer_id IS NULL

UNION ALL

-- ------------------------------------------------------------
-- 6. INVOICE SUBSCRIPTION FOREIGN KEYS
-- ------------------------------------------------------------
SELECT
    'invoice_subscription_fk_valid',
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
    CAST(COUNT(*) AS VARCHAR),
    '0 orphan rows'
FROM stg_invoices i
LEFT JOIN stg_subscriptions s
    ON i.subscription_id = s.subscription_id
WHERE s.subscription_id IS NULL

UNION ALL

-- ------------------------------------------------------------
-- 7. MOVEMENT TYPE DOMAIN
-- ------------------------------------------------------------
SELECT
    'movement_type_valid',
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
    CAST(COUNT(*) AS VARCHAR),
    '0 invalid movement rows'
FROM stg_subscription_months
WHERE movement_type NOT IN (
    'Retained',
    'New',
    'Expansion',
    'Contraction',
    'Churn',
    'Reactivation'
)
OR movement_type IS NULL

UNION ALL

-- ------------------------------------------------------------
-- 8. NULL FINANCIAL VALUES
-- ------------------------------------------------------------
SELECT
    'subscription_month_financial_values_not_null',
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
    CAST(COUNT(*) AS VARCHAR),
    '0 null financial rows'
FROM stg_subscription_months
WHERE mrr_usd IS NULL
   OR previous_mrr_usd IS NULL
   OR mrr_delta_usd IS NULL

UNION ALL

-- ------------------------------------------------------------
-- 9. NEGATIVE ENDING MRR
-- ------------------------------------------------------------
SELECT
    'ending_mrr_nonnegative',
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
    CAST(COUNT(*) AS VARCHAR),
    '0 negative MRR rows'
FROM stg_subscription_months
WHERE mrr_usd < 0

UNION ALL

-- ------------------------------------------------------------
-- 10. MRR BRIDGE RECONCILIATION
--
-- beginning MRR + delta = ending MRR
-- checked at monthly company level
-- ------------------------------------------------------------
SELECT
    'monthly_mrr_bridge_reconciles',
    CASE
        WHEN MAX(ABS(reconciliation_error)) < 0.01
        THEN 'PASS'
        ELSE 'FAIL'
    END,
    CAST(MAX(ABS(reconciliation_error)) AS VARCHAR),
    '< 0.01 absolute error'
FROM (
    SELECT
        period_month,
        SUM(previous_mrr_usd)
            + SUM(mrr_delta_usd)
            - SUM(mrr_usd) AS reconciliation_error
    FROM stg_subscription_months
    GROUP BY period_month
) x;-- Data quality checks placeholder.
