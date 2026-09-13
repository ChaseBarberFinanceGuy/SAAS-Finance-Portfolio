"""Deterministic finance snapshot for Management Flags."""
from __future__ import annotations
from typing import Any, Mapping

def build_snapshot(conn: Any, as_of_month: str, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the certified fact packet for one reporting scope.

    Milestone 1 will implement and reconcile the finance calculations.
    Monthly Billings is intentionally excluded until revalidated.
    """
    raise NotImplementedError(
        "Milestone 1: implement deterministic snapshot calculations "
        "from the certified SaaS source data."
    )
