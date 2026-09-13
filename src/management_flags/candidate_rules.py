"""
Stratum | Management Flags
Deterministic candidate-generation rules.

Turns a certified finance snapshot into structured candidate
observations. This module identifies possible management stories;
it does not decide final ranking or write executive commentary.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_CONFIG_PATH = REPO_ROOT / "config" / "management_flags.json"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def load_rules_config() -> dict[str, Any]:
    """Load management flag thresholds and weights."""

    with RULES_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _valid_number(value: Any) -> bool:
    """True only for usable finite numeric values."""

    if value is None:
        return False

    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _candidate(
    *,
    candidate_id: str,
    category: str,
    direction: str,
    rule_id: str,
    metric_ids: list[str],
    facts: dict[str, Any],
    trigger_value: float,
    actual_value: float,
    weight: float,
    rationale: str,
) -> dict[str, Any]:
    """
    Standard candidate structure.

    trigger_ratio is intentionally calculated here as a deterministic
    input to the materiality engine, but final scoring happens later.
    """

    trigger_ratio = (
        abs(actual_value) / abs(trigger_value)
        if trigger_value != 0
        else 0.0
    )

    return {
        "id": candidate_id,
        "category": category,
        "direction": direction,
        "rule_id": rule_id,
        "metric_ids": metric_ids,
        "facts": facts,
        "actual_value": actual_value,
        "trigger_value": trigger_value,
        "trigger_ratio": trigger_ratio,
        "weight": weight,
        "rationale": rationale,
    }


# ------------------------------------------------------------
# Rule engine
# ------------------------------------------------------------

def generate_candidates(
    snapshot: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate deterministic candidate observations from a finance snapshot.

    Returns all candidates that cross a configured trigger.
    Final scoring, deduplication, and selection happen in materiality.py.
    """

    if config is None:
        config = load_rules_config()

    rules = config["rules"]

    growth = snapshot.get("growth", {})
    scale = snapshot.get("scale", {})
    retention = snapshot.get("retention", {})
    concentration = snapshot.get("concentration", {})
    bridge = snapshot.get("bridge", {})

    candidates: list[dict[str, Any]] = []

    # ========================================================
    # 1. ARR YOY GROWTH
    # ========================================================

    arr_yoy = growth.get("arr_yoy_growth_pct")
    arr_rule = rules["arr_yoy_growth"]

    if (
        _valid_number(arr_yoy)
        and abs(arr_yoy) >= arr_rule["abs_trigger_pct"]
    ):
        candidates.append(
            _candidate(
                candidate_id="arr_yoy_growth",
                category="growth",
                direction="positive" if arr_yoy > 0 else "negative",
                rule_id="arr_yoy_growth",
                metric_ids=[
                    "current_arr",
                    "arr_yoy_growth_pct",
                ],
                facts={
                    "current_arr": scale.get("current_arr"),
                    "arr_yoy_growth_pct": arr_yoy,
                    "avg_ttm_arr": scale.get("avg_ttm_arr"),
                },
                actual_value=arr_yoy,
                trigger_value=arr_rule["abs_trigger_pct"],
                weight=arr_rule["weight"],
                rationale=(
                    "ARR year-over-year growth exceeded the configured "
                    "materiality threshold."
                ),
            )
        )

    # ========================================================
    # 2. NET MRR CHANGE
    # ========================================================

    net_mrr_change_pct = growth.get("net_mrr_change_pct")
    net_mrr_rule = rules["net_mrr_change"]

    if (
        _valid_number(net_mrr_change_pct)
        and abs(net_mrr_change_pct)
        >= net_mrr_rule["abs_trigger_pct"]
    ):
        candidates.append(
            _candidate(
                candidate_id="net_mrr_change",
                category="bridge",
                direction=(
                    "positive"
                    if net_mrr_change_pct > 0
                    else "negative"
                ),
                rule_id="net_mrr_change",
                metric_ids=[
                    "ending_mrr",
                    "new_mrr",
                    "expansion_mrr",
                    "reactivation_mrr",
                    "contraction_mrr",
                    "churned_mrr",
                ],
                facts={
                    "beginning_mrr": bridge.get("beginning_mrr"),
                    "ending_mrr": bridge.get("ending_mrr"),
                    "net_mrr_change": bridge.get("net_mrr_change"),
                    "net_mrr_change_pct": net_mrr_change_pct,
                    "new_mrr": bridge.get("new_mrr"),
                    "expansion_mrr": bridge.get("expansion_mrr"),
                    "reactivation_mrr": bridge.get(
                        "reactivation_mrr"
                    ),
                    "contraction_mrr": bridge.get(
                        "contraction_mrr"
                    ),
                    "churned_mrr": bridge.get("churned_mrr"),
                },
                actual_value=net_mrr_change_pct,
                trigger_value=net_mrr_rule["abs_trigger_pct"],
                weight=net_mrr_rule["weight"],
                rationale=(
                    "Net monthly MRR movement exceeded the configured "
                    "share-of-beginning-MRR threshold."
                ),
            )
        )

    # ========================================================
    # 3. NRR
    # ========================================================

    nrr = retention.get("nrr_12m")
    nrr_rule = rules["nrr"]

    if _valid_number(nrr):

        if nrr >= nrr_rule["high"]:
            candidates.append(
                _candidate(
                    candidate_id="nrr_high",
                    category="retention",
                    direction="positive",
                    rule_id="nrr",
                    metric_ids=["nrr_12m"],
                    facts={
                        "nrr_12m": nrr,
                        "logo_retention_12m": retention.get(
                            "logo_retention_12m"
                        ),
                        "nrr_mom_change_ppts": retention.get(
                            "nrr_mom_change_ppts"
                        ),
                    },
                    actual_value=nrr,
                    trigger_value=nrr_rule["high"],
                    weight=nrr_rule["weight"],
                    rationale=(
                        "NRR exceeded the configured high-retention "
                        "threshold."
                    ),
                )
            )

        elif nrr < nrr_rule["low"]:
            candidates.append(
                _candidate(
                    candidate_id="nrr_low",
                    category="retention",
                    direction="negative",
                    rule_id="nrr",
                    metric_ids=["nrr_12m"],
                    facts={
                        "nrr_12m": nrr,
                        "logo_retention_12m": retention.get(
                            "logo_retention_12m"
                        ),
                        "nrr_mom_change_ppts": retention.get(
                            "nrr_mom_change_ppts"
                        ),
                    },
                    actual_value=1 - nrr,
                    trigger_value=1 - nrr_rule["low"],
                    weight=nrr_rule["weight"],
                    rationale=(
                        "NRR fell below 100%, indicating erosion of the "
                        "beginning recurring-revenue base."
                    ),
                )
            )

    # ========================================================
    # 4. GRR
    # ========================================================

    grr = retention.get("grr_12m")
    grr_yoy_change = retention.get("grr_yoy_change_ppts")
    grr_rule = rules["grr"]

    grr_low = (
        _valid_number(grr)
        and grr < grr_rule["low"]
    )

    grr_changed = (
        _valid_number(grr_yoy_change)
        and abs(grr_yoy_change)
        >= grr_rule["yoy_change_ppts"]
    )

    if grr_low or grr_changed:

        if grr_low:
            actual = grr_rule["low"] / grr
            trigger = 1.0
        else:
            actual = abs(grr_yoy_change)
            trigger = grr_rule["yoy_change_ppts"]

        candidates.append(
            _candidate(
                candidate_id="grr",
                category="retention",
                direction=(
                    "negative"
                    if grr_low
                    or (
                        _valid_number(grr_yoy_change)
                        and grr_yoy_change < 0
                    )
                    else "positive"
                ),
                rule_id="grr",
                metric_ids=["grr_12m"],
                facts={
                    "grr_12m": grr,
                    "grr_yoy_change_ppts": grr_yoy_change,
                    "grr_mom_change_ppts": retention.get(
                        "grr_mom_change_ppts"
                    ),
                },
                actual_value=actual,
                trigger_value=trigger,
                weight=grr_rule["weight"],
                rationale=(
                    "GRR breached the configured floor or changed "
                    "materially versus the prior year."
                ),
            )
        )

    # ========================================================
    # 5. ACTIVE CUSTOMER YOY GROWTH
    # ========================================================

    customer_yoy = growth.get("active_customers_yoy_pct")
    customer_rule = rules["active_customer_yoy"]

    if (
        _valid_number(customer_yoy)
        and abs(customer_yoy)
        >= customer_rule["abs_trigger_pct"]
    ):
        candidates.append(
            _candidate(
                candidate_id="active_customer_yoy",
                category="customers",
                direction=(
                    "positive" if customer_yoy > 0 else "negative"
                ),
                rule_id="active_customer_yoy",
                metric_ids=["active_customers"],
                facts={
                    "active_customers": scale.get("active_customers"),
                    "active_customers_yoy_pct": customer_yoy,
                    "arr_yoy_growth_pct": growth.get(
                        "arr_yoy_growth_pct"
                    ),
                },
                actual_value=customer_yoy,
                trigger_value=customer_rule["abs_trigger_pct"],
                weight=customer_rule["weight"],
                rationale=(
                    "Active-customer growth exceeded the configured "
                    "year-over-year threshold."
                ),
            )
        )

    # ========================================================
    # 6. ARR PER ACCOUNT YOY
    # ========================================================

    arr_per_account_yoy = growth.get(
        "avg_arr_per_account_yoy_pct"
    )
    arpa_rule = rules["arr_per_account_yoy"]

    if (
        _valid_number(arr_per_account_yoy)
        and abs(arr_per_account_yoy)
        >= arpa_rule["abs_trigger_pct"]
    ):
        candidates.append(
            _candidate(
                candidate_id="arr_per_account_yoy",
                category="customer_economics",
                direction=(
                    "positive"
                    if arr_per_account_yoy > 0
                    else "negative"
                ),
                rule_id="arr_per_account_yoy",
                metric_ids=["avg_arr_per_account"],
                facts={
                    "avg_arr_per_account": scale.get(
                        "avg_arr_per_account"
                    ),
                    "avg_arr_per_account_yoy_pct": (
                        arr_per_account_yoy
                    ),
                    "arr_yoy_growth_pct": growth.get(
                        "arr_yoy_growth_pct"
                    ),
                    "active_customers_yoy_pct": growth.get(
                        "active_customers_yoy_pct"
                    ),
                },
                actual_value=arr_per_account_yoy,
                trigger_value=arpa_rule["abs_trigger_pct"],
                weight=arpa_rule["weight"],
                rationale=(
                    "Average ARR per active account changed beyond the "
                    "configured threshold."
                ),
            )
        )

    # ========================================================
    # 7. TOP-10 CUSTOMER CONCENTRATION
    # ========================================================

    top10 = concentration.get("top_10_arr_share")
    top10_yoy_change = concentration.get(
        "top_10_yoy_change_ppts"
    )
    concentration_rule = rules["top10_concentration"]

    concentration_high = (
        _valid_number(top10)
        and top10 >= concentration_rule["high"]
    )

    concentration_changed = (
        _valid_number(top10_yoy_change)
        and abs(top10_yoy_change)
        >= concentration_rule["change_ppts"]
    )

    if concentration_high or concentration_changed:

        if concentration_high:
            actual = top10
            trigger = concentration_rule["high"]
        else:
            actual = abs(top10_yoy_change)
            trigger = concentration_rule["change_ppts"]

        candidates.append(
            _candidate(
                candidate_id="top10_concentration",
                category="concentration",
                direction=(
                    "negative"
                    if concentration_high
                    or (
                        _valid_number(top10_yoy_change)
                        and top10_yoy_change > 0
                    )
                    else "positive"
                ),
                rule_id="top10_concentration",
                metric_ids=[
                    "top_10_arr_concentration"
                ],
                facts={
                    "top_5_arr_share": concentration.get(
                        "top_5_arr_share"
                    ),
                    "top_10_arr_share": top10,
                    "top_20_arr_share": concentration.get(
                        "top_20_arr_share"
                    ),
                    "top_10_yoy_change_ppts": top10_yoy_change,
                    "top_10_mom_change_ppts": concentration.get(
                        "top_10_mom_change_ppts"
                    ),
                },
                actual_value=actual,
                trigger_value=trigger,
                weight=concentration_rule["weight"],
                rationale=(
                    "Top-10 customer concentration exceeded its risk "
                    "threshold or changed materially."
                ),
            )
        )

    return candidates


# ------------------------------------------------------------
# Smoke test
# ------------------------------------------------------------

if __name__ == "__main__":

    from src.management_flags.snapshot import build_finance_snapshot

    snapshot = build_finance_snapshot("2026-06")
    candidates = generate_candidates(snapshot)

    print(
        json.dumps(
            candidates,
            indent=2,
            default=str,
        )
    )