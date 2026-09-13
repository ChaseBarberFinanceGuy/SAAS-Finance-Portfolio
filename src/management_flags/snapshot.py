"""
Stratum | Management Flags
Certified finance snapshot builder.

Creates the bounded deterministic fact packet used by the
Management Flags candidate-generation and materiality engines.
"""

from __future__ import annotations

from typing import Any

from src.metrics import (
    get_arr_bridge,
    get_company_kpis,
    get_concentration_metrics,
    get_customer_movements,
    get_retention_by_segment,
)


def _clean_value(value: Any) -> Any:
    """Convert pandas / numpy values into JSON-friendly Python values."""
    if value is None:
        return None

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (ValueError, AttributeError):
            pass

    return value


def _clean_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Return dictionary containing JSON-friendly scalar values."""
    return {
        key: _clean_value(value)
        for key, value in data.items()
    }


def build_finance_snapshot(as_of_month: str) -> dict[str, Any]:
    """
    Build the certified finance snapshot for Management Flags.

    Parameters
    ----------
    as_of_month:
        Reporting period in YYYY-MM format.

    Returns
    -------
    dict
        Bounded deterministic finance fact packet.
    """

    kpis = get_company_kpis(as_of_month)
    bridge = get_arr_bridge(as_of_month)
    concentration = get_concentration_metrics(as_of_month)

    segment_retention_df = get_retention_by_segment(as_of_month)

    segment_retention = [
        _clean_dict(record)
        for record in segment_retention_df.to_dict(orient="records")
    ]

    largest_movements_df = get_customer_movements(
        as_of_month=as_of_month,
        limit=10,
    )

    largest_movements = [
        _clean_dict(record)
        for record in largest_movements_df.to_dict(orient="records")
    ]

    snapshot = {
        "period": as_of_month,

        "scope": {
            "segment": "All",
            "region": "All",
            "plan": "All",
            "customer": "All",
        },

        "scale": {
            "ending_mrr": kpis.get("ending_mrr"),
            "current_arr": kpis.get("current_arr"),
            "avg_ttm_arr": kpis.get("avg_ttm_arr"),
            "active_customers": kpis.get("active_customers"),
            "avg_arr_per_account": kpis.get(
                "avg_arr_per_account"
            ),
        },

        "growth": {
            "arr_yoy_growth_pct": kpis.get(
                "arr_yoy_growth_pct"
            ),
            "active_customers_yoy_pct": kpis.get(
                "active_customers_yoy_pct"
            ),
            "avg_arr_per_account_yoy_pct": kpis.get(
                "avg_arr_per_account_yoy_pct"
            ),
            "net_mrr_change": kpis.get(
                "net_mrr_change"
            ),
            "net_mrr_change_pct": kpis.get(
                "net_mrr_change_pct"
            ),
        },

        "retention": {
            "nrr_12m": kpis.get("nrr_12m"),
            "grr_12m": kpis.get("grr_12m"),
            "logo_retention_12m": kpis.get(
                "logo_retention_12m"
            ),
            "logo_churn_12m": kpis.get(
                "logo_churn_12m"
            ),
            "nrr_mom_change_ppts": kpis.get(
                "nrr_mom_change_ppts"
            ),
            "grr_mom_change_ppts": kpis.get(
                "grr_mom_change_ppts"
            ),
            "grr_yoy_change_ppts": kpis.get(
                "grr_yoy_change_ppts"
            ),
        },

        "bridge": {
            "beginning_mrr": bridge.get(
                "beginning_mrr"
            ),
            "new_mrr": bridge.get(
                "new_mrr"
            ),
            "expansion_mrr": bridge.get(
                "expansion_mrr"
            ),
            "reactivation_mrr": bridge.get(
                "reactivation_mrr"
            ),
            "contraction_mrr": bridge.get(
                "contraction_mrr"
            ),
            "churned_mrr": bridge.get(
                "churned_mrr"
            ),
            "net_mrr_change": bridge.get(
                "net_mrr_change"
            ),
            "ending_mrr": bridge.get(
                "ending_mrr"
            ),
            "bridge_reconciliation_error": bridge.get(
                "bridge_reconciliation_error"
            ),
        },

        "concentration": {
            "top_5_arr_share": concentration.get(
                "top_5_arr_concentration"
            ),
            "top_10_arr_share": concentration.get(
                "top_10_arr_concentration"
            ),
            "top_20_arr_share": concentration.get(
                "top_20_arr_concentration"
            ),
            "top_10_mom_change_ppts": kpis.get(
                "top_10_concentration_mom_change_ppts"
            ),
            "top_10_yoy_change_ppts": kpis.get(
                "top_10_concentration_yoy_change_ppts"
            ),
        },

        "segment_retention": segment_retention,

        "largest_customer_movements": largest_movements,
    }

    return _clean_dict(snapshot)


if __name__ == "__main__":
    import json

    snapshot = build_finance_snapshot("2026-06")

    print(
        json.dumps(
            snapshot,
            indent=2,
            default=str,
        )
    )