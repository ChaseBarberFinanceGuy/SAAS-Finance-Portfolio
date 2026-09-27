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

from typing import Any

from src.finance_copilot.router import route_question
from src.finance_copilot.context_builder import build_copilot_context
from src.finance_copilot.answer_writer import write_copilot_answer
from src.finance_copilot.validator import validate_copilot_answer


def answer_finance_question(
    question: str,
    default_period: str | None = None,
) -> dict[str, Any]:
    """
    Answer one Finance Copilot question using the governed Stratum pipeline.

    The LLM never receives the full raw dataset. It receives only the
    router-approved, certified context packet.
    """

    route = route_question(
        question=question,
        default_period=default_period,
    )

    context = build_copilot_context(
        route=route,
    )

    response = write_copilot_answer(
        question=question,
        route=route,
        context=context,
    )

    validate_copilot_answer(
        response=response,
        route=route,
        context=context,
    )

    return response


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

    response = write_copilot_answer(
        question=question,
        route=route,
        context=context,
    )

    validate_copilot_answer(
        response=response,
        route=route,
        context=context,
    )

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
