-- KPI views placeh-- ============================================================
-- 04_kpi_views.sql
-- SAAS Finance Portolio
-- Certified monthly KPI layer
-- ============================================================


CREATE OR REPLACE VIEW vw_company_monthly_kpis AS

WITH monthly_scale AS (

    SELECT
        period_month,
        MIN(month_start_date) AS month_start_date,

        SUM(mrr_usd) AS ending_mrr,

        SUM(mrr_usd) * 12 AS current_arr,

        COUNT(DISTINCT customer_id) FILTER (
            WHERE mrr_usd > 0
        ) AS active_customers,

        (
            SUM(mrr_usd) * 12
        )
        /
        NULLIF(
            COUNT(DISTINCT customer_id) FILTER (
                WHERE mrr_usd > 0
            ),
            0
        ) AS avg_arr_per_account,

        SUM(mrr_usd)
        /
        NULLIF(
            COUNT(DISTINCT customer_id) FILTER (
                WHERE mrr_usd > 0
            ),
            0
        ) AS avg_mrr_per_account

    FROM vw_customer_monthly

    GROUP BY period_month
),


scale_windows AS (

    SELECT
        *,

        LAG(current_arr, 12) OVER (
            ORDER BY month_start_date
        ) AS current_arr_12m_prior,

        LAG(active_customers, 12) OVER (
            ORDER BY month_start_date
        ) AS active_customers_12m_prior,

        LAG(avg_arr_per_account, 12) OVER (
            ORDER BY month_start_date
        ) AS avg_arr_per_account_12m_prior,

        COUNT(*) OVER (
            ORDER BY month_start_date
            ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
        ) AS trailing_month_count,

        AVG(current_arr) OVER (
            ORDER BY month_start_date
            ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
        ) AS rolling_12m_avg_arr

    FROM monthly_scale
),


kpi_base AS (

    SELECT
        s.period_month,
        s.month_start_date,

        s.ending_mrr,
        s.current_arr,

        CASE
            WHEN s.trailing_month_count = 12
            THEN s.rolling_12m_avg_arr
            ELSE NULL
        END AS avg_ttm_arr,

        CASE
            WHEN s.current_arr_12m_prior IS NULL
              OR s.current_arr_12m_prior = 0
            THEN NULL
            ELSE
                s.current_arr
                / s.current_arr_12m_prior
                - 1
        END AS arr_yoy_growth_pct,

        s.active_customers,

        CASE
            WHEN s.active_customers_12m_prior IS NULL
              OR s.active_customers_12m_prior = 0
            THEN NULL
            ELSE
                s.active_customers * 1.0
                / s.active_customers_12m_prior
                - 1
        END AS active_customers_yoy_pct,

        s.avg_arr_per_account,

        CASE
            WHEN s.avg_arr_per_account_12m_prior IS NULL
              OR s.avg_arr_per_account_12m_prior = 0
            THEN NULL
            ELSE
                s.avg_arr_per_account
                / s.avg_arr_per_account_12m_prior
                - 1
        END AS avg_arr_per_account_yoy_pct,

        s.avg_mrr_per_account,

        r.nrr_12m,
        r.grr_12m,
        r.logo_retention_12m,
        r.logo_churn_12m,

        c.top_5_arr_concentration,
        c.top_10_arr_concentration,
        c.top_20_arr_concentration,

        b.beginning_mrr,
        b.new_mrr,
        b.expansion_mrr,
        b.reactivation_mrr,
        b.contraction_mrr,
        b.churned_mrr,
        b.net_mrr_change,

        CASE
            WHEN b.beginning_mrr IS NULL
              OR b.beginning_mrr = 0
            THEN NULL
            ELSE
                b.net_mrr_change
                / b.beginning_mrr
        END AS net_mrr_change_pct,

        b.ending_mrr AS bridge_ending_mrr,
        b.bridge_reconciliation_error

    FROM scale_windows s

    LEFT JOIN vw_retention_12m r
        ON s.period_month = r.period_month

    LEFT JOIN vw_customer_concentration c
        ON s.period_month = c.period_month

    LEFT JOIN vw_arr_bridge b
        ON s.period_month = b.period_month
)


SELECT
    *,

    (
        grr_12m
        - LAG(grr_12m, 12) OVER (
            ORDER BY month_start_date
        )
    ) * 100
        AS grr_yoy_change_ppts,

    (
        nrr_12m
        - LAG(nrr_12m, 1) OVER (
            ORDER BY month_start_date
        )
    ) * 100
        AS nrr_mom_change_ppts,

    (
        grr_12m
        - LAG(grr_12m, 1) OVER (
            ORDER BY month_start_date
        )
    ) * 100
        AS grr_mom_change_ppts,

    (
        top_10_arr_concentration
        - LAG(top_10_arr_concentration, 1) OVER (
            ORDER BY month_start_date
        )
    ) * 100
        AS top_10_concentration_mom_change_ppts,

    (
        top_10_arr_concentration
        - LAG(top_10_arr_concentration, 12) OVER (
            ORDER BY month_start_date
        )
    ) * 100
        AS top_10_concentration_yoy_change_ppts

FROM kpi_base;