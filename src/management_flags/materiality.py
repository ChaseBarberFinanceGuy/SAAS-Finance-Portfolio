"""
Stratum | Management Flags
Materiality scoring, story-family merging, deduplication, and selection.

This module decides which deterministic candidate observations deserve
executive attention before any LLM is called.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_CONFIG_PATH = REPO_ROOT / "config" / "management_flags.json"


# ------------------------------------------------------------
# Config
# ------------------------------------------------------------

def load_rules_config() -> dict[str, Any]:
    with RULES_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------
# Scoring
# ------------------------------------------------------------

def score_candidate(candidate: dict[str, Any]) -> float:
    """
    Convert trigger strength + strategic weight into a 0-100-ish score.

    Design:
    - 1.0x trigger ~= 60
    - stronger deviations rise quickly
    - weights preserve strategic priority
    - scores are capped at 100
    """

    ratio = max(float(candidate.get("trigger_ratio", 0.0)), 0.0)
    weight = max(float(candidate.get("weight", 1.0)), 0.0)

    # 1.0x = 60, 2.0x = 75, 3.0x = 85, 5.0x+ approaches 100.
    magnitude_score = 45.0 + min(ratio, 5.0) * 15.0

    # Keep weights meaningful without making lower-weight supporting
    # metrics impossible to surface.
    weight_multiplier = 0.7 + (0.3 * weight)

    score = magnitude_score * weight_multiplier

    return round(min(score, 100.0), 2)


# ------------------------------------------------------------
# Story-family helpers
# ------------------------------------------------------------

def _find(candidates: list[dict[str, Any]], candidate_id: str):
    return next(
        (c for c in candidates if c["id"] == candidate_id),
        None,
    )


def _combined_candidate(
    *,
    candidate_id: str,
    category: str,
    direction: str,
    member_candidates: list[dict[str, Any]],
    metric_ids: list[str],
    facts: dict[str, Any],
    rationale: str,
    score_bonus: float = 5.0,
) -> dict[str, Any]:
    """
    Merge related candidates into one richer management story.
    """

    base_score = max(
        member["score"]
        for member in member_candidates
    )

    combined_score = min(
        100.0,
        base_score + score_bonus,
    )

    return {
        "id": candidate_id,
        "category": category,
        "direction": direction,
        "metric_ids": metric_ids,
        "facts": facts,
        "score": round(combined_score, 2),
        "rationale": rationale,
        "merged_from": [
            member["id"]
            for member in member_candidates
        ],
    }


# ------------------------------------------------------------
# Growth story
# ------------------------------------------------------------

def merge_growth_story(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str]]:
    """
    Merge ARR growth + active customer growth + ARR/account growth.

    These metrics describe the composition of the same high-level
    growth story and should usually not appear as three separate flags.
    """

    arr = _find(candidates, "arr_yoy_growth")
    customers = _find(candidates, "active_customer_yoy")
    arpa = _find(candidates, "arr_per_account_yoy")

    members = [
        c for c in [arr, customers, arpa]
        if c is not None
    ]

    if len(members) < 2:
        return [], set()

    facts: dict[str, Any] = {}

    if arr:
        facts.update(arr.get("facts", {}))

    if customers:
        facts.update(customers.get("facts", {}))

    if arpa:
        facts.update(arpa.get("facts", {}))

    directions = {
        member.get("direction")
        for member in members
    }

    direction = (
        "positive"
        if directions == {"positive"}
        else "negative"
        if directions == {"negative"}
        else "mixed"
    )

    merged = _combined_candidate(
        candidate_id="growth_composition",
        category="growth",
        direction=direction,
        member_candidates=members,
        metric_ids=[
            "current_arr",
            "arr_yoy_growth_pct",
            "active_customers",
            "active_customers_yoy_pct",
            "avg_arr_per_account",
            "avg_arr_per_account_yoy_pct",
        ],
        facts=facts,
        rationale=(
            "ARR growth, active-customer growth, and ARR per account "
            "are related components of the same growth-composition story."
        ),
        score_bonus=5.0,
    )

    return [merged], {
        member["id"]
        for member in members
    }


# ------------------------------------------------------------
# Retention story
# ------------------------------------------------------------

def merge_retention_story(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str]]:
    """
    Merge NRR and GRR when both are material.

    A high NRR alongside weak GRR is especially decision-relevant:
    expansion strength is offsetting gross revenue leakage.
    """

    nrr = _find(candidates, "nrr_high")
    grr = _find(candidates, "grr")

    if not nrr or not grr:
        return [], set()

    nrr_value = nrr.get("facts", {}).get("nrr_12m")
    grr_value = grr.get("facts", {}).get("grr_12m")

    facts = {}

    facts.update(nrr.get("facts", {}))
    facts.update(grr.get("facts", {}))

    if (
        nrr_value is not None
        and grr_value is not None
        and nrr_value > 1
        and grr_value < 0.90
    ):
        direction = "mixed"
        rationale = (
            "NRR is above 100% while GRR is below the configured floor, "
            "showing expansion strength alongside meaningful gross leakage."
        )
        bonus = 10.0

    else:
        direction = "mixed"
        rationale = (
            "NRR and GRR are both material and should be interpreted "
            "together rather than as duplicate retention flags."
        )
        bonus = 5.0

    merged = _combined_candidate(
        candidate_id="retention_quality",
        category="retention",
        direction=direction,
        member_candidates=[nrr, grr],
        metric_ids=[
            "nrr_12m",
            "grr_12m",
            "logo_retention_12m",
        ],
        facts=facts,
        rationale=rationale,
        score_bonus=bonus,
    )

    return [merged], {"nrr_high", "grr"}


# ------------------------------------------------------------
# Final ranking
# ------------------------------------------------------------

def rank_and_select(
    candidates: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    max_flags: int | None = None,
) -> list[dict[str, Any]]:
    """
    Score, merge, dedupe, threshold, rank, and cap candidates.

    Returns zero to max_flags selected story candidates.
    """

    if config is None:
        config = load_rules_config()

    minimum_score = float(config.get("minimum_score", 60))

    if max_flags is None:
        max_flags = int(config.get("max_flags", 4))

    scored = []

    for candidate in candidates:
        item = deepcopy(candidate)
        item["score"] = score_candidate(item)
        scored.append(item)

    # --------------------------------------------------------
    # Merge related story families
    # --------------------------------------------------------

    merged: list[dict[str, Any]] = []
    consumed_ids: set[str] = set()

    growth_merged, growth_consumed = merge_growth_story(scored)
    merged.extend(growth_merged)
    consumed_ids.update(growth_consumed)

    retention_merged, retention_consumed = merge_retention_story(scored)
    merged.extend(retention_merged)
    consumed_ids.update(retention_consumed)

    # Keep unconsumed standalone candidates.
    for candidate in scored:
        if candidate["id"] not in consumed_ids:
            merged.append(candidate)

    # --------------------------------------------------------
    # Minimum materiality threshold
    # --------------------------------------------------------

    selected = [
        candidate
        for candidate in merged
        if candidate.get("score", 0) >= minimum_score
    ]

    # --------------------------------------------------------
    # Final sort
    # --------------------------------------------------------

    selected.sort(
        key=lambda x: x.get("score", 0),
        reverse=True,
    )

    # --------------------------------------------------------
    # Cap, never quota
    # --------------------------------------------------------

    selected = selected[:max_flags]

    # Rank only after final selection.
    for rank, candidate in enumerate(selected, start=1):
        candidate["rank"] = rank

    return selected


# ------------------------------------------------------------
# Smoke test
# ------------------------------------------------------------

if __name__ == "__main__":

    from src.management_flags.snapshot import build_finance_snapshot
    from src.management_flags.candidate_rules import generate_candidates

    snapshot = build_finance_snapshot("2026-06")
    candidates = generate_candidates(snapshot)
    selected = rank_and_select(candidates)

    print(
        json.dumps(
            selected,
            indent=2,
            default=str,
        )
    )