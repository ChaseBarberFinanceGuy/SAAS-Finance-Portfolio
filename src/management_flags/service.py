"""Single callable pipeline for Streamlit, MBR, and future APIs."""
from __future__ import annotations
from typing import Any, Callable
from .snapshot import build_snapshot
from .candidate_rules import generate_candidates
from .materiality import rank_and_select

def generate_management_flags(*, conn: Any, as_of_month: str, filters: dict[str, Any] | None = None,
                              max_flags: int = 4, rules_config: dict[str, Any],
                              writer: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    filters = filters or {}
    snapshot = build_snapshot(conn, as_of_month, filters)
    candidates = generate_candidates(snapshot, rules_config)
    selected = rank_and_select(
        candidates,
        minimum_score=float(rules_config.get("minimum_score", 60)),
        max_flags=min(max_flags, int(rules_config.get("max_flags", 4))),
    )
    if writer is None or not selected:
        return {
            "as_of_month": as_of_month,
            "filters": filters,
            "flags": [],
            "candidate_count": len(candidates),
            "selected_candidates": [c.__dict__ for c in selected],
            "snapshot": snapshot,
        }
    return writer(
        as_of_month=as_of_month,
        filters=filters,
        snapshot=snapshot,
        selected_candidates=[c.__dict__ for c in selected],
    )
