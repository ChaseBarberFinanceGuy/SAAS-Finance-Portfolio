"""Metric calculations will be
Stratum | Strategic Finance Lab
Certified metric access layer.

This module does not calculate headline finance metrics from raw data.
It queries the certified DuckDB views created by the SQL layer and
returns clean Python objects for the dashboard, management flags,
Finance Copilot, and automated MBR.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = REPO_ROOT / "database" / "stratum_finance.duckdb"
METRICS_CONFIG_PATH = REPO_ROOT / "config" / "metrics.json"


# ------------------------------------------------------------
# Connection / config
# ------------------------------------------------------------

def get_connection(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """
    Open the Stratum finance DuckDB database.

    Parameters
    ----------
    read_only:
        Use read-only mode by default for application queries.
    """
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"DuckDB database not found at: {DATABASE_PATH}\n"
            "Run src/ingestion.py first."
        )

    return duckdb.connect(
        str(DATABASE_PATH),
        read_only=read_only,
    )


def load_metric_catalog() -> dict[str, Any]:
    """Load config/metrics.json."""
    if not METRICS_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Metric catalog not found at: {METRICS_CONFIG_PATH}"
        )

    with METRICS_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_metric_definition(metric_id: str) -> dict[str, Any]:
    """
    Return one metric definition from config/metrics.json.
    """
    catalog = load_metric_catalog()

    metrics = catalog.get("metrics", {})

    if metric_id not in metrics:
        raise KeyError(f"Unknown metric_id: {metric_id}")

    return metrics[metric_id]


# ------------------------------------------------------------
# Period helpers
# ------------------------------------------------------------

def get_available_periods(
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[str]:
    """
    Return supported periods newest first.
    """
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT DISTINCT period_month
            FROM vw_company_monthly_kpis
            ORDER BY period_month DESC
            """
        ).fetchall()

        return [row[0] for row in rows]

    finally:
        if owns_connection:
            conn.close()


def get_latest_period(
    conn: duckdb.DuckDBPyConnection | None = None,
) -> str:
    """
    Return latest fully loaded period.
    """
    periods = get_available_periods(conn)

    if not periods:
        raise ValueError("No periods available in certified KPI view.")

    return periods[0]


def validate_period(
    as_of_month: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> None:
    """
    Confirm requested YYYY-MM exists in the certified KPI layer.
    """
    periods = get_available_periods(conn)

    if as_of_month not in periods:
        raise ValueError(
            f"Unsupported period: {as_of_month}. "
            f"Available range: {periods[-1]} through {periods[0]}"
        )


# ------------------------------------------------------------
# Certified company KPI access
# ------------------------------------------------------------

def get_company_kpis(
    as_of_month: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """
    Return certified company-level KPIs for one month.
    """
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        validate_period(as_of_month, conn)

        row = conn.execute(
            """
            SELECT
                period_month,
                month_start_date,

                ending_mrr,
                current_arr,
                avg_ttm_arr,
                arr_yoy_growth_pct,

                active_customers,
                active_customers_yoy_pct,

                avg_arr_per_account,
                avg_arr_per_account_yoy_pct,
                avg_mrr_per_account,

                nrr_12m,
                grr_12m,
                logo_retention_12m,
                logo_churn_12m,

                top_5_arr_concentration,
                top_10_arr_concentration,
                top_20_arr_concentration,

                beginning_mrr,
                new_mrr,
                expansion_mrr,
                reactivation_mrr,
                contraction_mrr,
                churned_mrr,
                net_mrr_change,
                net_mrr_change_pct,

                grr_yoy_change_ppts,
                nrr_mom_change_ppts,
                grr_mom_change_ppts,
                top_10_concentration_mom_change_ppts,
                top_10_concentration_yoy_change_ppts,

                bridge_ending_mrr,
                bridge_reconciliation_error

            FROM vw_company_monthly_kpis
            WHERE period_month = ?
            """,
            [as_of_month],
        ).fetchdf()

        if row.empty:
            raise ValueError(
                f"No certified KPI data found for {as_of_month}"
            )

        return row.iloc[0].to_dict()

    finally:
        if owns_connection:
            conn.close()


# ------------------------------------------------------------
# ARR bridge
# ------------------------------------------------------------

def get_arr_bridge(
    as_of_month: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """
    Return certified monthly MRR / ARR bridge.
    """
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        validate_period(as_of_month, conn)

        df = conn.execute(
            """
            SELECT
                period_month,
                month_start_date,

                beginning_mrr,
                new_mrr,
                expansion_mrr,
                reactivation_mrr,
                contraction_mrr,
                churned_mrr,
                net_mrr_change,
                ending_mrr,

                beginning_arr,
                ending_arr,
                net_arr_change,

                bridge_reconciliation_error

            FROM vw_arr_bridge
            WHERE period_month = ?
            """,
            [as_of_month],
        ).fetchdf()

        if df.empty:
            raise ValueError(
                f"No ARR bridge data found for {as_of_month}"
            )

        return df.iloc[0].to_dict()

    finally:
        if owns_connection:
            conn.close()


# ------------------------------------------------------------
# Retention
# ------------------------------------------------------------

def get_retention_metrics(
    as_of_month: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """
    Return company-level certified 12-month retention metrics.
    """
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        validate_period(as_of_month, conn)

        df = conn.execute(
            """
            SELECT
                period_month,
                month_start_date,
                beginning_cohort_mrr,
                ending_cohort_mrr,
                nrr_12m,
                grr_12m,
                beginning_logos,
                retained_logos,
                logo_retention_12m,
                logo_churn_12m

            FROM vw_retention_12m
            WHERE period_month = ?
            """,
            [as_of_month],
        ).fetchdf()

        if df.empty:
            return {
                "period_month": as_of_month,
                "nrr_12m": None,
                "grr_12m": None,
                "logo_retention_12m": None,
                "logo_churn_12m": None,
            }

        return df.iloc[0].to_dict()

    finally:
        if owns_connection:
            conn.close()


def get_retention_by_segment(
    as_of_month: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """
    Return certified 12-month retention by segment.
    """
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        validate_period(as_of_month, conn)

        return conn.execute(
            """
            SELECT
                period_month,
                segment,
                beginning_cohort_mrr,
                ending_cohort_mrr,
                nrr_12m,
                grr_12m,
                beginning_logos,
                retained_logos,
                logo_retention_12m

            FROM vw_retention_by_segment
            WHERE period_month = ?
            ORDER BY beginning_cohort_mrr DESC
            """,
            [as_of_month],
        ).fetchdf()

    finally:
        if owns_connection:
            conn.close()


# ------------------------------------------------------------
# Concentration
# ------------------------------------------------------------

def get_concentration_metrics(
    as_of_month: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """
    Return certified customer ARR concentration metrics.
    """
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        validate_period(as_of_month, conn)

        df = conn.execute(
            """
            SELECT
                period_month,
                month_start_date,
                top_5_arr_concentration,
                top_10_arr_concentration,
                top_20_arr_concentration

            FROM vw_customer_concentration
            WHERE period_month = ?
            """,
            [as_of_month],
        ).fetchdf()

        if df.empty:
            raise ValueError(
                f"No concentration data found for {as_of_month}"
            )

        return df.iloc[0].to_dict()

    finally:
        if owns_connection:
            conn.close()


# ------------------------------------------------------------
# Historical trend access
# ------------------------------------------------------------

def get_company_kpi_history(
    start_month: str | None = None,
    end_month: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """
    Return monthly certified KPI history.

    Parameters are inclusive YYYY-MM strings.
    """
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        conditions = []
        params: list[Any] = []

        if start_month is not None:
            conditions.append("period_month >= ?")
            params.append(start_month)

        if end_month is not None:
            conditions.append("period_month <= ?")
            params.append(end_month)

        where_clause = ""

        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT *
            FROM vw_company_monthly_kpis
            {where_clause}
            ORDER BY month_start_date
        """

        return conn.execute(query, params).fetchdf()

    finally:
        if owns_connection:
            conn.close()


# ------------------------------------------------------------
# Customer detail / movement access
# ------------------------------------------------------------

def get_customer_movements(
    as_of_month: str,
    movement_type: str | None = None,
    limit: int = 20,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """
    Return largest customer-level recurring-revenue movements
    for a selected month.
    """
    allowed_movements = {
        "New",
        "Expansion",
        "Reactivation",
        "Contraction",
        "Churn",
        "Retained",
    }

    if movement_type is not None and movement_type not in allowed_movements:
        raise ValueError(
            f"Unsupported movement_type: {movement_type}"
        )

    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        validate_period(as_of_month, conn)

        params: list[Any] = [as_of_month]

        movement_filter = ""

        if movement_type is not None:
            movement_filter = "AND movement_type = ?"
            params.append(movement_type)

        params.append(limit)

        return conn.execute(
            f"""
            SELECT
                period_month,
                customer_id,
                company_name,
                segment,
                region,
                tier,
                movement_type,
                previous_mrr_usd,
                mrr_delta_usd,
                mrr_usd,
                arr_usd

            FROM vw_customer_monthly

            WHERE period_month = ?
              {movement_filter}
              AND mrr_delta_usd <> 0

            ORDER BY ABS(mrr_delta_usd) DESC

            LIMIT ?
            """,
            params,
        ).fetchdf()

    finally:
        if owns_connection:
            conn.close()


def get_top_customers(
    as_of_month: str,
    limit: int = 20,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """
    Return largest customers by ARR for one month.
    """
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        validate_period(as_of_month, conn)

        return conn.execute(
            """
            SELECT
                customer_id,
                company_name,
                segment,
                region,
                tier,
                mrr_usd,
                arr_usd

            FROM vw_customer_monthly

            WHERE period_month = ?
              AND mrr_usd > 0

            ORDER BY arr_usd DESC

            LIMIT ?
            """,
            [as_of_month, limit],
        ).fetchdf()

    finally:
        if owns_connection:
            conn.close()


# ------------------------------------------------------------
# Data-quality status
# ------------------------------------------------------------

def get_data_quality_checks(
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """
    Return current certified data-quality checks.
    """
    owns_connection = conn is None

    if owns_connection:
        conn = get_connection()

    try:
        return conn.execute(
            """
            SELECT
                check_name,
                status,
                observed_value,
                expected_or_comparison

            FROM vw_data_quality_checks

            ORDER BY check_name
            """
        ).fetchdf()

    finally:
        if owns_connection:
            conn.close()


def all_data_quality_checks_pass(
    conn: duckdb.DuckDBPyConnection | None = None,
) -> bool:
    """
    True only when every registered data-quality check passes.
    """
    df = get_data_quality_checks(conn)

    if df.empty:
        return False

    return bool((df["status"] == "PASS").all())


# ------------------------------------------------------------
# Simple smoke test
# ------------------------------------------------------------

if __name__ == "__main__":
    latest = get_latest_period()

    print(f"Latest certified period: {latest}")
    print()

    kpis = get_company_kpis(latest)

    print("Certified KPIs")
    print("-" * 60)

    for key, value in kpis.items():
        print(f"{key}: {value}")

    print()
    print(
        "Data quality:",
        "PASS" if all_data_quality_checks_pass() else "FAIL",
    )