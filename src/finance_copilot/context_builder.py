"""
Stratum | Finance Copilot
Bounded context builder with temporal support.

Takes a governed router result and returns only the facts / definitions that
the Finance Copilot is permitted to see.

It reuses the existing certified finance snapshot:
    src.management_flags.snapshot.build_finance_snapshot

Temporal behavior:
- anchor / point -> one certified monthly snapshot
- comparison     -> two certified monthly snapshots + deterministic deltas
- range          -> one certified snapshot per month + deterministic start/end deltas

No new business metric definitions are created here. Temporal differences are
deterministic presentation calculations over already-certified metrics.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.management_flags.snapshot import build_finance_snapshot
from src.management_flags.service import get_management_flags


REPO_ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = REPO_ROOT / "config" / "metrics.json"
_MISSING = object()


class FinanceCopilotContextError(ValueError):
    """Raised when approved context cannot be assembled safely."""


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _find_key(value: Any, target_key: str) -> Any:
    """
    Recursively find an exact certified metric key in a nested snapshot.
    """

    value = _plain(value)

    if isinstance(value, Mapping):
        if target_key in value:
            return value[target_key]

        for child in value.values():
            found = _find_key(child, target_key)

            if found is not _MISSING:
                return found

    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for child in value:
            found = _find_key(child, target_key)

            if found is not _MISSING:
                return found

    return _MISSING


def _load_metric_catalog(
    metrics_path: str | Path = METRICS_PATH,
) -> Any:
    path = Path(metrics_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Metric catalog not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _find_metric_definition(
    catalog: Any,
    metric_id: str,
) -> dict[str, Any] | None:
    """
    Locate a metric definition in common metrics.json structures.
    """

    catalog = _plain(catalog)

    if isinstance(catalog, Mapping):
        if metric_id in catalog and isinstance(
            catalog[metric_id],
            Mapping,
        ):
            result = dict(catalog[metric_id])
            result.setdefault("id", metric_id)
            return result

        metric_identifier = (
            catalog.get("id")
            or catalog.get("metric_id")
            or catalog.get("key")
        )

        if metric_identifier == metric_id:
            return dict(catalog)

        for child in catalog.values():
            found = _find_metric_definition(
                child,
                metric_id,
            )

            if found:
                return found

    elif isinstance(catalog, Sequence) and not isinstance(
        catalog,
        (str, bytes, bytearray),
    ):
        for child in catalog:
            found = _find_metric_definition(
                child,
                metric_id,
            )

            if found:
                return found

    return None


# ---------------------------------------------------------------------
# Certified snapshot helpers
# ---------------------------------------------------------------------


def _facts_for_period(
    period: str,
    approved_metrics: list[str],
) -> dict[str, Any]:
    """
    Return only approved metrics from one certified monthly snapshot.
    """

    snapshot = build_finance_snapshot(period)

    facts: dict[str, Any] = {}
    missing: list[str] = []

    for metric_id in approved_metrics:
        value = _find_key(
            snapshot,
            metric_id,
        )

        if value is _MISSING:
            missing.append(metric_id)
        else:
            facts[metric_id] = value

    if missing:
        raise FinanceCopilotContextError(
            f"Approved metrics were not found in the certified "
            f"snapshot for {period}: "
            + ", ".join(missing)
        )

    return facts


def _numeric_delta(
    comparison_value: Any,
    current_value: Any,
) -> dict[str, float] | None:
    """
    Calculate deterministic point-to-point change for numeric certified facts.

    This is not a new business KPI. It is comparison metadata supplied so the
    LLM does not perform subtraction or percentage-change math itself.
    """

    if isinstance(comparison_value, bool) or isinstance(
        current_value,
        bool,
    ):
        return None

    if not isinstance(
        comparison_value,
        (int, float),
    ) or not isinstance(
        current_value,
        (int, float),
    ):
        return None

    comparison = float(comparison_value)
    current = float(current_value)

    if not (
        math.isfinite(comparison)
        and math.isfinite(current)
    ):
        return None

    absolute_change = current - comparison

    percent_change = None

    if comparison != 0:
        percent_change = absolute_change / abs(comparison)

    return {
        "absolute_change": absolute_change,
        "percent_change": percent_change,
    }


def _build_comparison_context(
    approved_metrics: list[str],
    comparison_period: str,
    current_period: str,
) -> dict[str, Any]:
    comparison_facts = _facts_for_period(
        comparison_period,
        approved_metrics,
    )

    current_facts = _facts_for_period(
        current_period,
        approved_metrics,
    )

    deltas: dict[str, Any] = {}

    for metric_id in approved_metrics:
        delta = _numeric_delta(
            comparison_facts.get(metric_id),
            current_facts.get(metric_id),
        )

        if delta is not None:
            deltas[metric_id] = delta

    return {
        "comparison_period": comparison_period,
        "current_period": current_period,
        "comparison_facts": comparison_facts,
        "current_facts": current_facts,
        "deltas": deltas,
    }


def _build_range_context(
    approved_metrics: list[str],
    periods: list[str],
) -> dict[str, Any]:
    if not periods:
        raise FinanceCopilotContextError(
            "Temporal range contains no reporting periods."
        )

    series: list[dict[str, Any]] = []

    for period in periods:
        series.append(
            {
                "period": period,
                "facts": _facts_for_period(
                    period,
                    approved_metrics,
                ),
            }
        )

    start_period = periods[0]
    end_period = periods[-1]

    start_facts = series[0]["facts"]
    end_facts = series[-1]["facts"]

    deltas: dict[str, Any] = {}

    for metric_id in approved_metrics:
        delta = _numeric_delta(
            start_facts.get(metric_id),
            end_facts.get(metric_id),
        )

        if delta is not None:
            deltas[metric_id] = delta

    return {
        "start_period": start_period,
        "end_period": end_period,
        "period_count": len(periods),
        "series": series,
        "start_facts": start_facts,
        "end_facts": end_facts,
        "deltas": deltas,
    }


# ---------------------------------------------------------------------
# Public context builder
# ---------------------------------------------------------------------


def build_copilot_context(
    route: dict[str, Any],
    metrics_path: str | Path = METRICS_PATH,
) -> dict[str, Any]:
    """
    Build the bounded context packet consumed by the answer writer.

    The router is the authority for:
    - supported intent,
    - approved metric bundle,
    - deterministic time interpretation.
    """

    status = route.get("status")
    intent = route.get("intent")
    period = route.get("period")
    time_context = route.get("time") or {}

    packet: dict[str, Any] = {
        "status": status,
        "intent": intent,
        "period": period,
        "time": time_context,
        "allowed_analysis": list(
            route.get(
                "allowed_analysis",
                [],
            )
        ),
        "facts": {},
        "definitions": {},
    }

    # -------------------------------------------------------------
    # Unsupported routes
    # -------------------------------------------------------------

    if status == "unsupported":
        packet["message"] = route.get("message")
        packet["unsupported_metrics"] = route.get(
            "unsupported_metrics",
            [],
        )
        packet["unsupported_details"] = route.get(
            "unsupported_details",
            [],
        )
        packet["supported_domains"] = route.get(
            "supported_domains",
            [],
        )

        return packet

    # -------------------------------------------------------------
    # Existing Management Flags service
    # -------------------------------------------------------------

    if intent == "management_summary":
        management_period = (
            time_context.get("target_period")
            or time_context.get("current_period")
            or time_context.get("end_period")
            or period
        )

        if not management_period:
            raise FinanceCopilotContextError(
                "Management summary requires a reporting period."
            )

        packet["management_flags"] = get_management_flags(
            management_period
        )

        return packet

    # -------------------------------------------------------------
    # Metric definition requests
    # -------------------------------------------------------------

    if intent == "metric_definition":
        metric_id = route.get("definition_metric")

        if not metric_id:
            raise FinanceCopilotContextError(
                "Could not identify the metric definition requested."
            )

        catalog = _load_metric_catalog(
            metrics_path
        )

        definition = _find_metric_definition(
            catalog,
            metric_id,
        )

        if not definition:
            raise FinanceCopilotContextError(
                f"Metric definition not found for {metric_id!r}."
            )

        packet["definitions"][metric_id] = definition

        return packet

    # -------------------------------------------------------------
    # Metric routes
    # -------------------------------------------------------------

    approved_metrics = list(
        route.get(
            "metrics",
            [],
        )
    )

    if not approved_metrics:
        if route.get("dynamic_metric_selection"):
            packet["requires_metric_selection"] = True

        return packet

    mode = time_context.get("mode", "anchor")

    # -------------------------------------------------------------
    # Range
    # -------------------------------------------------------------

    if mode == "range":
        periods = list(
            time_context.get(
                "periods",
                [],
            )
        )

        packet["range"] = _build_range_context(
            approved_metrics=approved_metrics,
            periods=periods,
        )

        # Keep end-period facts in `facts` for backward compatibility and
        # for concise answers that need the current endpoint.
        packet["facts"] = dict(
            packet["range"]["end_facts"]
        )

    # -------------------------------------------------------------
    # Comparison
    # -------------------------------------------------------------

    elif mode == "comparison":
        comparison_period = time_context.get(
            "comparison_period"
        )

        current_period = (
            time_context.get("current_period")
            or time_context.get("anchor_period")
        )

        if not comparison_period or not current_period:
            raise FinanceCopilotContextError(
                "Comparison route is missing one or both reporting periods."
            )

        packet["comparison"] = _build_comparison_context(
            approved_metrics=approved_metrics,
            comparison_period=comparison_period,
            current_period=current_period,
        )

        packet["facts"] = dict(
            packet["comparison"]["current_facts"]
        )

    # -------------------------------------------------------------
    # Point / anchor
    # -------------------------------------------------------------

    else:
        target_period = (
            time_context.get("target_period")
            or time_context.get("anchor_period")
            or period
        )

        if not target_period:
            raise FinanceCopilotContextError(
                "A reporting period is required for metric questions."
            )

        packet["period"] = target_period
        packet["facts"] = _facts_for_period(
            target_period,
            approved_metrics,
        )

    # -------------------------------------------------------------
    # Partially supported requests
    # -------------------------------------------------------------

    if status == "partially_supported":
        packet["unsupported_metrics"] = route.get(
            "unsupported_metrics",
            [],
        )

        packet["message"] = route.get(
            "message"
        )

    return packet


# ---------------------------------------------------------------------
# Local smoke test
# ---------------------------------------------------------------------


if __name__ == "__main__":
    from src.finance_copilot.router import route_question

    examples = [
        "What was ARR one year ago?",
        "What was ARR 6 months ago?",
        "Compare ARR to one year ago",
        "Show ARR over the past 6 months",
        "How has NRR changed over the past 12 months?",
        "What is 12-month NRR?",
        "What is CAC?",
    ]

    for question in examples:
        print("=" * 80)
        print(question)

        route = route_question(
            question,
            default_period="2026-06",
        )

        print("ROUTE")
        print(
            json.dumps(
                route,
                indent=2,
                default=str,
            )
        )

        context = build_copilot_context(
            route
        )

        print("CONTEXT")
        print(
            json.dumps(
                context,
                indent=2,
                default=str,
            )
        )

    print()
    print("FINANCE COPILOT TEMPORAL CONTEXT: PASS")
