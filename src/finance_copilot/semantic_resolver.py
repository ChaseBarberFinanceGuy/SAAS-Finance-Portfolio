"""
Stratum | Finance Copilot
Bounded semantic resolver.

Used only when deterministic routing cannot confidently identify a supported
intent/metric. The LLM may interpret language, but it may only select from
approved intents, metric IDs, dimensions, and temporal modes.

It never receives raw finance data and never calculates finance metrics.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "finance_copilot.json"
DEFAULT_METRICS_PATH = REPO_ROOT / "config" / "metrics.json"

DEFAULT_MODEL = os.getenv(
    "FINANCE_COPILOT_ROUTER_MODEL",
    os.getenv("FINANCE_COPILOT_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.6")),
)

ALLOWED_TEMPORAL_MODES = {"anchor", "point", "range", "comparison"}
ALLOWED_DIMENSIONS = {"region", "segment", "plan_tier"}
ALLOWED_INTENTS = {
    "current_arr", "ending_mrr", "arr_growth", "mrr_bridge", "nrr", "grr",
    "retention_quality", "logo_retention", "active_customers",
    "customer_growth", "arr_per_account", "customer_economics",
    "concentration", "management_summary", "metric_definition",
}


class FinanceCopilotSemanticResolutionError(ValueError):
    """Raised when a semantic route cannot be validated safely."""


def _load_json(path: str | Path) -> Any:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _metric_catalog_summary(
    config: dict[str, Any],
    metrics_catalog: Any,
) -> list[dict[str, Any]]:
    supported_ids = set(config.get("supported_metric_ids", []))
    results: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            metric_id = value.get("id") or value.get("metric_id") or value.get("key")
            if metric_id in supported_ids:
                results.append(
                    {
                        "id": metric_id,
                        "name": value.get("display_name") or value.get("name") or metric_id,
                        "definition": value.get("definition") or value.get("description") or "",
                    }
                )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(metrics_catalog)

    found_ids = {item["id"] for item in results}
    for metric_id in sorted(supported_ids - found_ids):
        results.append(
            {
                "id": metric_id,
                "name": metric_id.replace("_", " ").title(),
                "definition": "",
            }
        )
    return results


def _intent_catalog(config: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for intent_id, item in config.get("intents", {}).items():
        if intent_id in ALLOWED_INTENTS:
            result.append(
                {
                    "intent": intent_id,
                    "metric_ids": list(item.get("metrics", [])),
                    "allowed_analysis": list(item.get("allowed_analysis", [])),
                }
            )
    return result


def resolve_semantically(
    question: str,
    *,
    deterministic_time: dict[str, Any] | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    metrics_path: str | Path = DEFAULT_METRICS_PATH,
) -> dict[str, Any]:
    """
    Interpret an otherwise ambiguous question using only governed choices.

    confidence is a routing heuristic, not a calibrated probability.
    """

    config = _load_json(config_path)
    metrics_catalog = _load_json(metrics_path)

    allowed_metric_ids = set(config.get("supported_metric_ids", []))

    prompt_packet = {
        "question": question,
        "deterministic_time": deterministic_time,
        "allowed_intents": _intent_catalog(config),
        "allowed_metrics": _metric_catalog_summary(config, metrics_catalog),
        "allowed_temporal_modes": sorted(ALLOWED_TEMPORAL_MODES),
        "allowed_dimensions": sorted(ALLOWED_DIMENSIONS),
    }

    instructions = """
You are a bounded semantic router for a strategic-finance copilot.

Interpret the user's wording and map it only to supplied governed choices.

Rules:
- Never invent a metric ID, intent, dimension, or temporal mode.
- Never calculate or answer the finance question.
- Prefer deterministic_time when present; do not override a clear date interpretation.
- "customer retention" or "logo retention" generally means logo retention.
- "revenue retention" maps to NRR/GRR depending on wording.
- "over the past 12 months" usually asks for a time series/range.
- "12-month NRR" or "12-month customer retention" can instead describe the
  trailing metric itself at one reporting date.
- Identify comparison, trend, breakdown, summary, point, or definition intent.
- confidence is a 0-1 routing heuristic, not a probability.
- Give a concise interpretation sentence.
- If another interpretation is plausible, provide it.
"""

    schema = {
        "type": "object",
        "properties": {
            "intent": {"type": ["string", "null"]},
            "metric_ids": {"type": "array", "items": {"type": "string"}},
            "analysis_type": {
                "type": "string",
                "enum": ["point", "trend", "comparison", "breakdown", "summary", "definition"],
            },
            "temporal_mode": {
                "type": "string",
                "enum": sorted(ALLOWED_TEMPORAL_MODES),
            },
            "range_months": {"type": ["integer", "null"]},
            "dimension": {"type": ["string", "null"]},
            "dimension_value": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "interpretation": {"type": "string"},
            "alternative_interpretation": {"type": ["string", "null"]},
        },
        "required": [
            "intent", "metric_ids", "analysis_type", "temporal_mode",
            "range_months", "dimension", "dimension_value", "confidence",
            "interpretation", "alternative_interpretation",
        ],
        "additionalProperties": False,
    }

    client = OpenAI()
    response = client.responses.create(
        model=DEFAULT_MODEL,
        instructions=instructions,
        input=json.dumps(prompt_packet, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "finance_copilot_semantic_route",
                "schema": schema,
                "strict": True,
            }
        },
    )

    result = json.loads(response.output_text)

    intent = result.get("intent")
    metric_ids = list(result.get("metric_ids", []))
    temporal_mode = result.get("temporal_mode")
    dimension = result.get("dimension")
    confidence = float(result.get("confidence", 0.0))

    if intent is not None and intent not in ALLOWED_INTENTS:
        raise FinanceCopilotSemanticResolutionError(
            f"Semantic resolver returned unapproved intent: {intent!r}"
        )

    unknown_metrics = set(metric_ids) - allowed_metric_ids
    if unknown_metrics:
        raise FinanceCopilotSemanticResolutionError(
            "Semantic resolver returned unapproved metric IDs: "
            + ", ".join(sorted(unknown_metrics))
        )

    if temporal_mode not in ALLOWED_TEMPORAL_MODES:
        raise FinanceCopilotSemanticResolutionError(
            f"Invalid temporal mode: {temporal_mode!r}"
        )

    if dimension is not None and dimension not in ALLOWED_DIMENSIONS:
        raise FinanceCopilotSemanticResolutionError(
            f"Invalid dimension: {dimension!r}"
        )

    result["confidence"] = max(0.0, min(1.0, confidence))
    result["resolver"] = "llm_bounded"
    return result


if __name__ == "__main__":
    examples = [
        "How are we doing with keeping customers?",
        "Compare revenue retention to last year.",
        "How does ARR break down geographically?",
    ]

    for question in examples:
        print("=" * 80)
        print(question)
        print(json.dumps(resolve_semantically(question), indent=2))

    print()
    print("SEMANTIC RESOLVER: PASS")
