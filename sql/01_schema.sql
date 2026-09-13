-- ============================================================
-- 01_schema.sql
-- SAAS Finance Portfolio
-- Normalized staging layer over raw DuckDB tables
-- ============================================================

-- ------------------------------------------------------------
-- CUSTOMERS
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW stg_customers AS
SELECT
    CAST(customer_id AS VARCHAR)              AS customer_id,
    company_name,
    country,
    region,
    industry,
    segment,
    employees_band,
    CAST(signup_date AS DATE)                 AS signup_date,
    acquisition_channel,
    SUBSTR(CAST(cohort_month AS VARCHAR), 1, 7) AS cohort_month,
    customer_status,
    TRY_CAST(churn_date AS DATE)              AS churn_date
FROM customers;


-- ------------------------------------------------------------
-- PLANS
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW stg_plans AS
SELECT
    CAST(plan_id AS VARCHAR)                  AS plan_id,
    plan_name,
    tier,
    billing_interval,
    CAST(list_price_usd AS DOUBLE)            AS list_price_usd,
    CAST(monthly_price_usd AS DOUBLE)         AS monthly_price_usd,
    CAST(billing_months AS INTEGER)           AS billing_months,
    CAST(seats_included AS INTEGER)           AS seats_included,
    CAST(extra_seat_price_usd AS DOUBLE)      AS extra_seat_price_usd,
    is_active,
    TRY_CAST(launched_date AS DATE)           AS launched_date
FROM plans;


-- ------------------------------------------------------------
-- SUBSCRIPTIONS
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW stg_subscriptions AS
SELECT
    CAST(subscription_id AS VARCHAR)          AS subscription_id,
    CAST(customer_id AS VARCHAR)              AS customer_id,
    CAST(plan_id AS VARCHAR)                  AS plan_id,
    CAST(start_date AS DATE)                  AS start_date,
    TRY_CAST(end_date AS DATE)                AS end_date,
    subscription_status,
    billing_interval,
    CAST(seats AS INTEGER)                    AS seats,
    CAST(discount_pct AS DOUBLE)              AS discount_pct,
    CAST(mrr_usd AS DOUBLE)                   AS mrr_usd,
    CAST(contract_term_months AS INTEGER)     AS contract_term_months,
    auto_renew
FROM subscriptions;


-- ------------------------------------------------------------
-- SUBSCRIPTION MONTHS
--
-- This is the primary historical recurring-revenue fact.
-- period_month is normalized to YYYY-MM from month_start_date.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW stg_subscription_months AS
SELECT
    CAST(record_id AS VARCHAR)                AS record_id,
    CAST(customer_id AS VARCHAR)              AS customer_id,
    CAST(subscription_id AS VARCHAR)          AS subscription_id,
    CAST(plan_id AS VARCHAR)                  AS plan_id,

    CAST(month_start_date AS DATE)            AS month_start_date,
    STRFTIME(
        CAST(month_start_date AS DATE),
        '%Y-%m'
    )                                         AS period_month,

    is_active,
    CAST(seats AS INTEGER)                    AS seats,
    CAST(mrr_usd AS DOUBLE)                   AS mrr_usd,
    CAST(previous_mrr_usd AS DOUBLE)          AS previous_mrr_usd,
    CAST(mrr_delta_usd AS DOUBLE)             AS mrr_delta_usd,
    movement_type,
    CAST(tenure_months AS INTEGER)            AS tenure_months,
    SUBSTR(CAST(cohort_month AS VARCHAR), 1, 7) AS cohort_month,
    currency
FROM subscription_months;


-- ------------------------------------------------------------
-- INVOICES
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW stg_invoices AS
SELECT
    CAST(invoice_id AS VARCHAR)               AS invoice_id,
    CAST(customer_id AS VARCHAR)              AS customer_id,
    CAST(subscription_id AS VARCHAR)          AS subscription_id,

    CAST(invoice_date AS DATE)                AS invoice_date,
    STRFTIME(
        DATE_TRUNC('month', CAST(invoice_date AS DATE)),
        '%Y-%m'
    )                                         AS invoice_month,

    TRY_CAST(billing_period_start AS DATE)    AS billing_period_start,
    TRY_CAST(billing_period_end AS DATE)      AS billing_period_end,

    CAST(months_covered AS INTEGER)           AS months_covered,
    CAST(amount_usd AS DOUBLE)                AS amount_usd,
    CAST(discount_usd AS DOUBLE)              AS discount_usd,
    CAST(subtotal_usd AS DOUBLE)              AS subtotal_usd,
    CAST(tax_usd AS DOUBLE)                   AS tax_usd,
    CAST(total_usd AS DOUBLE)                 AS total_usd,

    invoice_status,
    payment_method,
    CAST(days_to_payment AS DOUBLE)           AS days_to_payment,
    currency
FROM invoices;-- Database schema placeholder.
