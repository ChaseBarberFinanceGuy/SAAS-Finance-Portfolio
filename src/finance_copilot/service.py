"""
Stratum | Finance Copilot
Service layer.

Provides one clean entry point for the application:

    answer_finance_question(
        question="What drove MRR in June 2026?",
        default_period="2026-06",
    )

Pipeline:
user question
    -> deterministic router
    -> bounded certified context
    -> constrained LLM answer writer
    -> deterministic validator
    -> validated response
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.finance_copilot.router import route_question
from src.finance_copilot.context_builder import build_copilot_context
from src.finance_copilot.answer_writer import (
    _format_context_for_display,
    _metric_catalog,
    write_copilot_answer,
)
from src.finance_copilot.validator import (
    FinanceCopilotValidationError,
    validate_copilot_answer,
)


def _certified_point_answer(
    route: dict[str, Any], context: dict[str, Any],
) -> dict[str, Any] | None:
    metrics = route.get("metrics", [])
    time = route.get("time") or {}
    if (
        route.get("status") != "supported"
        or time.get("mode", "anchor") not in {"point", "anchor"}
        or len(metrics) != 1
        or "range" in context
        or "comparison" in context
    ):
        return None

    metric_id = metrics[0]
    period = context.get("period")
    if not isinstance(period, str):
        return None
    try:
        period_label = datetime.strptime(period, "%Y-%m").strftime("%B %Y")
    except ValueError:
        return None

    # Use only the point fact and its deterministic display.
    facts = context.get("facts", {})
    if metric_id not in facts:
        return None
    formatted = _format_context_for_display({"facts": {metric_id: facts[metric_id]}})
    display = formatted["facts"].get(f"{metric_id}_display")
    label = {
        "nrr_12m": "12-month NRR",
        "grr_12m": "12-month GRR",
    }.get(metric_id) or _metric_catalog().get(metric_id, {}).get("label")
    if not display or not label:
        return None

    return {
        "answer": f"{label} was {display} as of {period_label}.",
        "source_metrics": [metric_id],
        "status": "supported",
    }


def _write_validated_answer(
    question: str, route: dict[str, Any], context: dict[str, Any],
) -> dict[str, Any]:
    response = write_copilot_answer(question=question, route=route, context=context)
    try:
        validate_copilot_answer(response=response, route=route, context=context)
    except FinanceCopilotValidationError as failure:
        response = write_copilot_answer(
            question=question,
            route=route,
            context=context,
            repair_guidance=str(failure),
        )
        try:
            validate_copilot_answer(response=response, route=route, context=context)
        except FinanceCopilotValidationError:
            fallback = _certified_point_answer(route, context)
            if fallback is None:
                raise
            validate_copilot_answer(response=fallback, route=route, context=context)
            return fallback
    return response


def answer_finance_question(
    question: str,
    default_period: str | None = None,
) -> dict[str, Any]:
    """Answer one question using the governed Stratum pipeline."""
    route = route_question(question=question, default_period=default_period)
    context = build_copilot_context(route=route)
    return _write_validated_answer(question, route, context)


def answer_finance_question_debug(
    question: str,
    default_period: str | None = None,
) -> dict[str, Any]:
    """
    Development/debug version of the service.

    Returns the route and bounded context in addition to the validated answer.
    Do not expose this payload directly in the public portfolio UI.
    """

    route = route_question(
        question=question,
        default_period=default_period,
    )

    context = build_copilot_context(
        route=route,
    )

    response = _write_validated_answer(question, route, context)

    return {
        "question": question,
        "route": route,
        "context": context,
        "response": response,
        "validated": True,
    }


if __name__ == "__main__":
    import json

    questions = [
        "What drove MRR in June 2026?",
        "How is retention overall?",
        "What is CAC?",
    ]

    for question in questions:
        print("=" * 80)
        print(question)

        result = answer_finance_question_debug(
            question=question,
            default_period="2026-06",
        )

        print(
            json.dumps(
                result,
                indent=2,
                default=str,
            )
        )

    print()
    print("FINANCE COPILOT SERVICE PIPELINE: PASS")
