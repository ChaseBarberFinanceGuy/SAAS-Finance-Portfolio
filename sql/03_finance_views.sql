-- ============================================================
-- 03_finance_views.sql
-- SAAS Finance Portolio
-- Certified analytical finance views
-- ============================================================


-- ============================================================
-- 1. CUSTOMER MONTHLY
-- Enriched customer-month recurring-revenue fact
-- ============================================================

CREATE OR REPLACE VIEW vw_customer_monthly AS
SELECT
    sm.period_month,
    sm.month_start_date,

    sm.customer_id,
    c.company_name,

    sm.subscription_id,
    sm.plan_id,

    c.segment,
    c.region,
    c.country,
    c.industry,
    c.acquisition_channel,

    p.plan_name,
    p.tier,
    p.billing_interval,

    sm.cohort_month,
    sm.tenure_months,
    sm.seats,
    sm.is_active,

    sm.mrr_usd,
    sm.previous_mrr_usd,
    sm.mrr_delta_usd,
    sm.movement_type,

    sm.mrr_usd * 12 AS arr_usd

FROM stg_subscription_months sm

LEFT JOIN stg_customers c
    ON sm.customer_id = c.customer_id

LEFT JOIN stg_plans p
    ON sm.plan_id = p.plan_id;


-- ============================================================
-- 2. MONTHLY ARR / MRR BRIDGE
-- ============================================================

CREATE OR REPLACE VIEW vw_arr_bridge AS
SELECT
    period_month,
    MIN(month_start_date) AS month_start_date,

    SUM(previous_mrr_usd) AS beginning_mrr,

    SUM(
        CASE
            WHEN movement_type = 'New'
            THEN mrr_delta_usd
            ELSE 0
        END
    ) AS new_mrr,

    SUM(
        CASE
            WHEN movement_type = 'Expansion'
            THEN mrr_delta_usd
            ELSE 0
        END
    ) AS expansion_mrr,

    SUM(
        CASE
            WHEN movement_type = 'Reactivation'
            THEN mrr_delta_usd
            ELSE 0
        END
    ) AS reactivation_mrr,

    ABS(
        SUM(
            CASE
                WHEN movement_type = 'Contraction'
                THEN mrr_delta_usd
                ELSE 0
            END
        )
    ) AS contraction_mrr,

    ABS(
        SUM(
            CASE
                WHEN movement_type = 'Churn'
                THEN mrr_delta_usd
                ELSE 0
            END
        )
    ) AS churned_mrr,

    SUM(mrr_delta_usd) AS net_mrr_change,

    SUM(mrr_usd) AS ending_mrr,

    SUM(previous_mrr_usd) * 12 AS beginning_arr,
    SUM(mrr_usd) * 12          AS ending_arr,

    SUM(mrr_delta_usd) * 12    AS net_arr_change,

    (
        SUM(mrr_usd)
        - (
            SUM(previous_mrr_usd)
            + SUM(mrr_delta_usd)
        )
    ) AS bridge_reconciliation_error

FROM vw_customer_monthly

GROUP BY period_month;


-- ============================================================
-- 3. COMPANY 12-MONTH RETENTION
--
-- Beginning cohort = customers with MRR > 0 exactly
-- 12 months before selected month.
-- New customers after beginning date are excluded.
-- ============================================================

CREATE OR REPLACE VIEW vw_retention_12m AS

WITH months AS (
    SELECT DISTINCT
        month_start_date AS as_of_month
    FROM vw_customer_monthly
),

beginning_cohort AS (
    SELECT
        m.as_of_month,
        b.customer_id,
        b.mrr_usd AS beginning_mrr
    FROM months m

    JOIN vw_customer_monthly b
        ON b.month_start_date =
           m.as_of_month - INTERVAL '12 months'

    WHERE b.mrr_usd > 0
),

cohort_with_end AS (
    SELECT
        bc.as_of_month,
        bc.customer_id,
        bc.beginning_mrr,
        COALESCE(e.mrr_usd, 0) AS ending_mrr
    FROM beginning_cohort bc

    LEFT JOIN vw_customer_monthly e
        ON e.customer_id = bc.customer_id
       AND e.month_start_date = bc.as_of_month
)

SELECT
    STRFTIME(as_of_month, '%Y-%m') AS period_month,
    as_of_month AS month_start_date,

    SUM(beginning_mrr) AS beginning_cohort_mrr,
    SUM(ending_mrr)    AS ending_cohort_mrr,

    SUM(ending_mrr)
        / NULLIF(SUM(beginning_mrr), 0)
        AS nrr_12m,

    SUM(
        LEAST(ending_mrr, beginning_mrr)
    )
        / NULLIF(SUM(beginning_mrr), 0)
        AS grr_12m,

    COUNT(*) AS beginning_logos,

    COUNT(*) FILTER (
        WHERE ending_mrr > 0
    ) AS retained_logos,

    COUNT(*) FILTER (
        WHERE ending_mrr > 0
    ) * 1.0
        / NULLIF(COUNT(*), 0)
        AS logo_retention_12m,

    1
    - (
        COUNT(*) FILTER (
            WHERE ending_mrr > 0
        ) * 1.0
        / NULLIF(COUNT(*), 0)
    ) AS logo_churn_12m

FROM cohort_with_end

GROUP BY as_of_month;


-- ============================================================
-- 4. SEGMENT 12-MONTH RETENTION
-- ============================================================

CREATE OR REPLACE VIEW vw_retention_by_segment AS

WITH months AS (
    SELECT DISTINCT
        month_start_date AS as_of_month
    FROM vw_customer_monthly
),

beginning_cohort AS (
    SELECT
        m.as_of_month,
        b.customer_id,
        b.segment,
        b.mrr_usd AS beginning_mrr
    FROM months m

    JOIN vw_customer_monthly b
        ON b.month_start_date =
           m.as_of_month - INTERVAL '12 months'

    WHERE b.mrr_usd > 0
),

cohort_with_end AS (
    SELECT
        bc.as_of_month,
        bc.customer_id,
        bc.segment,
        bc.beginning_mrr,
        COALESCE(e.mrr_usd, 0) AS ending_mrr
    FROM beginning_cohort bc

    LEFT JOIN vw_customer_monthly e
        ON e.customer_id = bc.customer_id
       AND e.month_start_date = bc.as_of_month
)

SELECT
    STRFTIME(as_of_month, '%Y-%m') AS period_month,
    as_of_month AS month_start_date,
    segment,

    SUM(beginning_mrr) AS beginning_cohort_mrr,
    SUM(ending_mrr)    AS ending_cohort_mrr,

    SUM(ending_mrr)
        / NULLIF(SUM(beginning_mrr), 0)
        AS nrr_12m,

    SUM(
        LEAST(ending_mrr, beginning_mrr)
    )
        / NULLIF(SUM(beginning_mrr), 0)
        AS grr_12m,

    COUNT(*) AS beginning_logos,

    COUNT(*) FILTER (
        WHERE ending_mrr > 0
    ) AS retained_logos,

    COUNT(*) FILTER (
        WHERE ending_mrr > 0
    ) * 1.0
        / NULLIF(COUNT(*), 0)
        AS logo_retention_12m

FROM cohort_with_end

GROUP BY
    as_of_month,
    segment;


-- ============================================================
-- 5. CUSTOMER CONCENTRATION
-- ============================================================

CREATE OR REPLACE VIEW vw_customer_concentration AS

WITH ranked AS (
    SELECT
        period_month,
        month_start_date,
        customer_id,
        mrr_usd,

        ROW_NUMBER() OVER (
            PARTITION BY period_month
            ORDER BY mrr_usd DESC
        ) AS revenue_rank

    FROM vw_customer_monthly

    WHERE mrr_usd > 0
),

monthly AS (
    SELECT
        period_month,
        MIN(month_start_date) AS month_start_date,

        SUM(mrr_usd) AS total_mrr,

        SUM(mrr_usd) FILTER (
            WHERE revenue_rank <= 5
        ) AS top_5_mrr,

        SUM(mrr_usd) FILTER (
            WHERE revenue_rank <= 10
        ) AS top_10_mrr,

        SUM(mrr_usd) FILTER (
            WHERE revenue_rank <= 20
        ) AS top_20_mrr

    FROM ranked

    GROUP BY period_month
)

SELECT
    period_month,
    month_start_date,

    top_5_mrr
        / NULLIF(total_mrr, 0)
        AS top_5_arr_concentration,

    top_10_mrr
        / NULLIF(total_mrr, 0)
        AS top_10_arr_concentration,

    top_20_mrr
        / NULLIF(total_mrr, 0)
        AS top_20_arr_concentration

FROM monthly;


-- ============================================================
-- 6. COHORT RETENTION
-- ============================================================

CREATE OR REPLACE VIEW vw_cohort_retention AS

WITH cohort_monthly AS (
    SELECT
        cohort_month,
        period_month,
        MIN(month_start_date) AS month_start_date,

        COUNT(*) FILTER (
            WHERE mrr_usd > 0
        ) AS active_customers,

        SUM(mrr_usd) AS cohort_mrr

    FROM vw_customer_monthly

    GROUP BY
        cohort_month,
        period_month
),

cohort_baseline AS (
    SELECT
        cohort_month,

        active_customers AS starting_customers,
        cohort_mrr       AS starting_mrr

    FROM cohort_monthly

    WHERE period_month = cohort_month
)

SELECT
    cm.cohort_month,
    cm.period_month,
    cm.month_start_date,

    DATE_DIFF(
        'month',
        CAST(cm.cohort_month || '-01' AS DATE),
        cm.month_start_date
    ) AS months_since_cohort,

    cm.active_customers,
    cm.cohort_mrr,

    cb.starting_customers,
    cb.starting_mrr,

    cm.active_customers * 1.0
        / NULLIF(cb.starting_customers, 0)
        AS logo_retention_pct,

    cm.cohort_mrr
        / NULLIF(cb.starting_mrr, 0)
        AS revenue_retention_pct

FROM cohort_monthly cm

LEFT JOIN cohort_baseline cb
    ON cm.cohort_month = cb.cohort_month;


-- ============================================================
-- 7. MONTHLY INVOICE SUMMARY
--
-- Important:
-- This is invoice value / billings, NOT GAAP recognized revenue.
-- ============================================================

CREATE OR REPLACE VIEW vw_invoice_summary AS
SELECT
    invoice_month,

    SUM(subtotal_usd) AS net_invoice_value,

    SUM(total_usd) AS total_invoice_value,

    COUNT(*) AS invoice_count,

    AVG(days_to_payment) AS avg_days_to_payment,

    COUNT(*) FILTER (
        WHERE invoice_status = 'Paid'
    ) AS paid_invoice_count

FROM stg_invoices

GROUP BY invoice_month;-- Finance views placeholder.
