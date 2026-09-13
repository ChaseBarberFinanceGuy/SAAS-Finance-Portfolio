"""
Stratum | Strategic Finance Lab
DuckDB database build / ingestion script.

Loads the raw Prime Levels CSV files into DuckDB, then executes
the certified SQL transformation layer in sequence.
"""

from pathlib import Path

import duckdb


# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = REPO_ROOT / "data" / "raw"
DATABASE_DIR = REPO_ROOT / "database"
DATABASE_PATH = DATABASE_DIR / "stratum_finance.duckdb"
SQL_DIR = REPO_ROOT / "sql"


RAW_TABLES = {
    "customers": DATA_DIR / "customers.csv",
    "plans": DATA_DIR / "plans.csv",
    "subscriptions": DATA_DIR / "subscriptions.csv",
    "subscription_months": DATA_DIR / "subscription_months.csv",
    "invoices": DATA_DIR / "invoices.csv",
}


SQL_FILES = [
    "01_schema.sql",
    "02_data_quality.sql",
    "03_finance_views.sql",
    "04_kpi_views.sql",
]


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def validate_files():
    """Fail early if an expected source or SQL file is missing."""

    missing = []

    for path in RAW_TABLES.values():
        if not path.exists():
            missing.append(path)

    for filename in SQL_FILES:
        path = SQL_DIR / filename
        if not path.exists():
            missing.append(path)

    if missing:
        missing_text = "\n".join(f" - {path}" for path in missing)
        raise FileNotFoundError(
            f"Required files are missing:\n{missing_text}"
        )


def load_raw_tables(conn):
    """Load source CSV files as persistent DuckDB tables."""

    print("\nLoading raw source tables...")

    for table_name, csv_path in RAW_TABLES.items():

        print(f"  Loading {table_name}...")

        conn.execute(
            f"""
            CREATE OR REPLACE TABLE {table_name} AS
            SELECT *
            FROM read_csv_auto(
                ?,
                header = true,
                sample_size = -1
            )
            """,
            [str(csv_path)],
        )

        row_count = conn.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).fetchone()[0]

        print(f"    {row_count:,} rows")


def run_sql_layer(conn):
    """Execute SQL transformations in dependency order."""

    print("\nBuilding certified SQL layer...")

    for filename in SQL_FILES:
        sql_path = SQL_DIR / filename

        print(f"  Running {filename}...")

        sql = sql_path.read_text(encoding="utf-8")
        conn.execute(sql)

        print("    complete")


def show_validation(conn):
    """Print key validation results after the build."""

    print("\nDATA QUALITY CHECKS")
    print("-" * 70)

    rows = conn.execute(
        """
        SELECT
            check_name,
            status,
            observed_value,
            expected_or_comparison
        FROM vw_data_quality_checks
        ORDER BY check_name
        """
    ).fetchall()

    for row in rows:
        print(row)

    print("\nJUNE 2026 KPI CHECK")
    print("-" * 70)

    kpi = conn.execute(
        """
        SELECT
            period_month,
            ending_mrr,
            current_arr,
            avg_ttm_arr,
            arr_yoy_growth_pct,
            active_customers,
            nrr_12m,
            grr_12m,
            top_10_arr_concentration
        FROM vw_company_monthly_kpis
        WHERE period_month = '2026-06'
        """
    ).fetchdf()

    print(kpi.to_string(index=False))

    print("\nJUNE 2026 ARR BRIDGE")
    print("-" * 70)

    bridge = conn.execute(
        """
        SELECT
            period_month,
            beginning_mrr,
            new_mrr,
            expansion_mrr,
            reactivation_mrr,
            contraction_mrr,
            churned_mrr,
            net_mrr_change,
            ending_mrr,
            bridge_reconciliation_error
        FROM vw_arr_bridge
        WHERE period_month = '2026-06'
        """
    ).fetchdf()

    print(bridge.to_string(index=False))


# ------------------------------------------------------------
# Build
# ------------------------------------------------------------

def build_database():
    validate_files()

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Building database:")
    print(f"  {DATABASE_PATH}")

    conn = duckdb.connect(str(DATABASE_PATH))

    try:
        load_raw_tables(conn)
        run_sql_layer(conn)
        show_validation(conn)

        print("\nDatabase build complete.")

    finally:
        conn.close()


if __name__ == "__main__":
    build_database()