"""
Stratum | Finance Copilot
Bounded LLM answer writer.

The writer receives:
- the original user question,
- the governed route,
- only the approved certified context.

It is not allowed to calculate new finance metrics or introduce facts outside
the supplied context.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from dotenv import load_dotenv
load_dotenv()


DEFAULT_MODEL = os.getenv(
    "FINANCE_COPILOT_MODEL",
    os.getenv("OPENAI_MODEL", "gpt-5.6"),
)

DISPLAY_FORMAT_RULES = """
DISPLAY FORMATTING RULES

Use consistent executive formatting within each answer.

Currency:
- Every monetary value must include a $ sign.
- Values >= $1M: use millions with two decimals, e.g. $4.70M, $5.59M.
- Values >= $1K and < $1M: use whole thousands when practical, e.g. $883K.
- Do not write 4.70M or 5.59M without the currency symbol.
- When comparing the same metric across periods, use the same display unit
  and decimal precision for all compared values.

Percentages:
- Normally use one decimal place, e.g. 18.8%, 82.7%.
- Use the same precision for compared percentages.

Counts:
- Use whole numbers with commas, e.g. 1,245 customers.

Consistency:
- Never switch formatting conventions for the same metric within one answer.
- Prefer concise executive notation over long raw numbers.
"""

SYSTEM_INSTRUCTIONS = """
You are Stratum Finance Copilot, an executive finance explanation layer.

You are NOT the finance calculation engine.

Rules:
1. Use only facts, metric definitions, management flags, and limitations
   explicitly supplied in the context packet.
2. Do not calculate new metrics, percentages, ratios, averages, forecasts,
   deltas, causes, or recommendations.
3. Do not add metrics that are not present in the context packet.
4. Numeric presentation formatting is allowed. Examples:
   - 5586735.12 may be written as $5.6M.
   - 0.5019046 may be written as 50.2%.
   Formatting is allowed; deriving a new numeric fact is not.
5. If the context says part of the question is unsupported, answer the
   supported portion and explicitly identify the unsupported portion.
6. If the context is unsupported, do not improvise an answer.
7. Do not claim causality unless the context explicitly contains causal
   evidence.
8. Keep the answer concise and useful to a finance executive.
9. Return JSON only, matching this schema exactly:

{
  "answer": "string",
  "source_metrics": ["metric_id"],
  "status": "supported | partially_supported | unsupported"
}

source_metrics must contain only metric IDs actually used in the answer.
For definitions or management-summary responses, source_metrics may be empty
when no direct metric list is appropriate.
{DISPLAY_FORMAT_RULES}
""".strip()




def _deterministic_unsupported_answer(
    route: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Unsupported routes do not need an LLM call."""

    message = (
        context.get("message")
        or route.get("message")
        or "That analysis is outside the current certified scope "
           "of Stratum Finance Copilot."
    )

    details = context.get("unsupported_details", [])

    if details:
        reason_text = " ".join(
            f"{item.get('display_name', item.get('metric_id', 'Metric'))}: "
            f"{item.get('reason', '')}"
            for item in details
        ).strip()

        if reason_text:
            message = f"{message} {reason_text}"

    return {
        "answer": message,
        "source_metrics": [],
        "status": "unsupported",
    }


def write_copilot_answer(
    question: str,
    route: dict[str, Any],
    context: dict[str, Any],
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """
    Write one bounded Finance Copilot response.

    Unsupported requests are answered deterministically without an API call.
    """

    status = route.get("status", "unsupported")

    if status == "unsupported":
        return _deterministic_unsupported_answer(
            route=route,
            context=context,
        )

    if context.get("requires_metric_selection"):
        return {
            "answer": (
                "That comparison requires an explicit supported metric "
                "selection before I can answer it."
            ),
            "source_metrics": [],
            "status": "unsupported",
        }

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. The Finance Copilot writer "
            "uses the same OpenAI API credential as the existing AI layer."
        )

    client = OpenAI(api_key=api_key)

    user_payload = {
        "question": question,
        "route": route,
        "context": context,
    }

    response = client.responses.create(
        model=model,
        instructions=SYSTEM_INSTRUCTIONS,
        input=json.dumps(
            user_payload,
            indent=2,
            default=str,
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "finance_copilot_answer",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "source_metrics": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "status": {
                            "type": "string",
                            "enum": [
                                "supported",
                                "partially_supported",
                                "unsupported",
                            ],
                        },
                    },
                    "required": [
                        "answer",
                        "source_metrics",
                        "status",
                    ],
                    "additionalProperties": False,
                },
            }
        },
    )

    raw = response.output_text

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Finance Copilot writer returned invalid JSON."
        ) from exc


if __name__ == "__main__":
    from src.finance_copilot.context_builder import build_copilot_context
    from src.finance_copilot.router import route_question

    question = "What drove MRR in June 2026?"

    route = route_question(
        question,
        default_period="2026-06",
    )

    context = build_copilot_context(route)

    print(
        json.dumps(
            write_copilot_answer(
                question=question,
                route=route,
                context=context,
            ),
            indent=2,
        )
    )
