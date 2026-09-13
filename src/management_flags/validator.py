"""Validation for generated Management Flags."""
from __future__ import annotations
from typing import Any

class ManagementFlagValidationError(ValueError):
    pass

def validate_response(response: dict[str, Any], *, selected_candidates: list[dict[str, Any]],
                      known_metric_ids: set[str], as_of_month: str,
                      filters: dict[str, Any] | None = None) -> bool:
    flags = response.get("flags")
    if not isinstance(flags, list):
        raise ManagementFlagValidationError("Response must contain a flags list.")
    if len(flags) > 4:
        raise ManagementFlagValidationError("Management Flags are capped at four.")
    selected_categories = {c.get("category") for c in selected_candidates}
    for flag in flags:
        sources = flag.get("source_metrics")
        if not sources:
            raise ManagementFlagValidationError("Every flag needs source_metrics.")
        unknown = set(sources) - known_metric_ids
        if unknown:
            raise ManagementFlagValidationError(f"Unknown source metric(s): {sorted(unknown)}")
        if selected_categories and flag.get("category") not in selected_categories:
            raise ManagementFlagValidationError("Flag does not map to a selected candidate.")
    response.setdefault("as_of_month", as_of_month)
    response.setdefault("filters", filters or {})
    return True
