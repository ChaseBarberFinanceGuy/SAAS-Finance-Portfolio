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
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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

Copy supplied display strings exactly, including signs, units, and precision.
The deterministic formatter uses the following conventions:

Currency:
- Every monetary value must include a $ sign.
- Values >= $1M: use millions with two decimals, e.g. $4.70M, $5.59M.
- Values >= $1K and < $1M: use whole thousands when practical, e.g. $883K.
- Do not write 4.70M or 5.59M without the currency symbol.

Percentages:
- Normally use one decimal place, e.g. 18.8%, 82.7%.
- Use the same precision for compared percentages.

Counts:
- Use whole numbers with commas, e.g. 1,245 customers.

Consistency:
- Absolute rate deltas use two decimals and the words percentage points.
- Relative deltas use signed percentages with one decimal place.
- Do not override supplied display strings to change units or precision.
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
4. Use supplied *_display fields verbatim for numeric claims. Do not
   round, scale, calculate, or reformat raw numeric values yourself.
   Raw values are retained only for validation. If a numeric value has
   no supplied display field, omit that numeric claim.
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
""".strip().replace("{DISPLAY_FORMAT_RULES}", DISPLAY_FORMAT_RULES)




def _metric_kind(metric_id: str, metadata: dict[str, Any]) -> str | None:
    """Prefer declared units; use metric names only, never numeric magnitude."""
    for key in ("value_type", "metric_type", "data_type", "format", "unit", "units"):
        unit = str(metadata.get(key, "")).lower().strip()
        if unit in {"currency", "money", "dollars", "usd", "$"}:
            return "currency"
        if unit in {"rate", "ratio", "percentage", "percent", "%", "fraction"}:
            return "rate"
        if unit in {"count", "integer", "customers", "logos", "seats"}:
            return "count"
    name = metric_id.lower()
    if any(token in name for token in ("retention", "churn_rate", "margin", "conversion", "penetration", "growth_rate")) or name.endswith(("_rate", "_pct", "_percent", "_ratio")):
        return "rate"
    if any(token in name.split("_") for token in ("arr", "mrr", "revenue", "cash", "cost", "expense", "profit", "ebitda", "arpu", "arpa", "acv", "ltv", "cac")):
        return "currency"
    if any(token in name.split("_") for token in ("count", "customers", "customer", "logos", "logo", "seats", "headcount", "employees", "users", "contracts")):
        return "count"
    return None


def _display_number(value: Any, kind: str | None, *, delta: bool = False) -> str | None:
    """Format fractional rates without altering certified raw values."""
    if kind is None or isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    magnitude = abs(number)
    sign = "-" if number < 0 else ("+" if delta and number > 0 else "")
    if kind == "currency":
        if magnitude >= 1_000_000:
            body = f"${(magnitude / 1_000_000).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}M"
        elif magnitude >= 1_000:
            body = f"${(magnitude / 1_000).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}K"
        else:
            body = f"${magnitude.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
    elif kind == "count":
        body = f"{magnitude.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}"
    elif kind == "points":
        body = f"{(magnitude * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f} percentage points"
    else:
        body = f"{(magnitude * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):.1f}%"
    return sign + body


def _format_context_for_display(context: dict[str, Any]) -> dict[str, Any]:
    """Add display siblings on a copy; leave all raw values and caller data intact.

    Supports metric-keyed maps, metric_id records, period-keyed series,
    and lists of records. Unknown metric units are intentionally not guessed.
    Rates and relative changes are certified fractions (0.827 means 82.7%).
    """
    formatted = deepcopy(context)
    metadata: dict[str, dict[str, Any]] = {}

    def collect(node: Any, metric: str = "") -> None:
        if isinstance(node, list):
            for item in node:
                collect(item, metric)
        elif isinstance(node, dict):
            current = str(node.get("metric_id") or metric)
            if current:
                metadata.setdefault(current, {}).update({
                    key: node[key] for key in ("value_type", "metric_type", "data_type", "format", "unit", "units") if key in node
                })
            for key, item in node.items():
                if isinstance(item, (dict, list)):
                    declared_kind = _metric_kind(key, item) if isinstance(item, dict) else None
                    collect(item, key if declared_kind or _metric_kind(key, {}) else current)

    collect(context)
    absolute_keys = {"absolute_change", "absolute_delta", "delta", "change"}
    relative_keys = {"percent_change", "percentage_change", "relative_change", "relative_delta", "pct_change"}
    value_keys = {"value", "raw_value", "start_value", "end_value", "current_value", "comparison_value", "start", "end", "current", "comparison"}

    def walk(node: Any, metric: str = "", deltas: bool = False) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, metric, deltas)
            return
        if not isinstance(node, dict):
            return
        current = str(node.get("metric_id") or metric)
        kind = _metric_kind(current, {**metadata.get(current, {}), **node})
        for key, value in list(node.items()):
            if key.endswith("_display"):
                continue
            key_kind = _metric_kind(key, metadata.get(key, {}))
            if isinstance(value, (dict, list)):
                walk(value, key if key_kind or key in metadata else current, deltas)
                continue
            display_kind = None
            signed = False
            if deltas and key in relative_keys:
                display_kind, signed = "rate", True
            elif deltas and key in absolute_keys:
                display_kind, signed = ("points" if kind == "rate" else kind), True
            elif key in value_keys:
                display_kind = kind
            elif key_kind:
                display_kind = "points" if deltas and key_kind == "rate" else key_kind
                signed = deltas
            display = _display_number(value, display_kind, delta=signed)
            if display is not None:
                node[f"{key}_display"] = display

    walk(formatted.get("facts"))
    for section, keys in (
        ("range", ("series", "start_facts", "end_facts", "deltas")),
        ("comparison", ("comparison_facts", "current_facts", "deltas")),
    ):
        block = formatted.get(section)
        if isinstance(block, dict):
            for key in keys:
                walk(block.get(key), deltas=key == "deltas")
    return formatted


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
        "context": _format_context_for_display(context),
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
