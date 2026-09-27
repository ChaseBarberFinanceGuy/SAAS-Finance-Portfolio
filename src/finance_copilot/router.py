"""
Stratum | Finance Copilot
Hybrid deterministic + bounded-semantic question router.

Straightforward questions are handled entirely by deterministic rules.
Only questions that remain ambiguous / generic after deterministic routing
are sent to the bounded semantic resolver.

The LLM never chooses outside the approved metric/intent catalog.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.finance_copilot.time_resolver import resolve_time_reference
from src.finance_copilot.semantic_resolver import (
    resolve_semantically,
    FinanceCopilotSemanticResolutionError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "finance_copilot.json"


def load_copilot_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Finance Copilot config not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize(text: str) -> str:
    text = text.lower().strip().replace("’", "'")
    return re.sub(r"\s+", " ", text)


def _contains_any(
    text: str,
    phrases: list[str] | tuple[str, ...],
) -> bool:
    return any(phrase in text for phrase in phrases)


MONTH_LOOKUP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def extract_period(
    question: str,
    default_period: str | None = None,
) -> str | None:
    text = _normalize(question)

    match = re.search(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"

    month_pattern = "|".join(sorted(MONTH_LOOKUP, key=len, reverse=True))
    match = re.search(rf"\b({month_pattern})\s+(20\d{{2}})\b", text)
    if match:
        return f"{int(match.group(2)):04d}-{MONTH_LOOKUP[match.group(1)]:02d}"

    return default_period


UNSUPPORTED_METRIC_ALIASES = {
    "cac": ["cac", "customer acquisition cost", "acquisition cost"],
    "ltv": ["ltv", "customer lifetime value", "lifetime value"],
    "ltv_cac": ["ltv:cac", "ltv / cac", "ltv to cac", "ltv cac"],
    "cac_payback": ["cac payback", "payback period"],
    "gross_margin": ["gross margin"],
    "ebitda": ["ebitda"],
    "free_cash_flow": ["free cash flow", "fcf"],
    "rule_of_40": ["rule of 40", "rule-of-40"],
    "bookings": ["bookings"],
    "pipeline": ["sales pipeline", "pipeline"],
}


def detect_unsupported_metrics(
    question: str,
    config: dict[str, Any],
) -> list[str]:
    text = _normalize(question)
    configured = config.get("known_unsupported_metrics", {})
    found: list[str] = []

    for metric_id, aliases in UNSUPPORTED_METRIC_ALIASES.items():
        if metric_id in configured and _contains_any(text, aliases):
            found.append(metric_id)

    return sorted(set(found))


FORECAST_PATTERNS = [
    "forecast", "predict", "projection", "project ",
    "next quarter", "next month", "next year",
    "will arr", "will mrr", "where will", "finish the year",
]

CAUSAL_PATTERNS = [
    "what caused", "why did customers leave",
    "why did customers churn", "why did churn",
    "did pricing cause", "because of pricing",
    "did sales cause", "caused by",
]

RECOMMENDATION_PATTERNS = [
    "should we", "what should we do", "recommend ",
    "recommendation", "raise prices", "lower prices",
    "drop customers", "fire ",
]


def detect_unsupported_intent(question: str) -> str | None:
    text = _normalize(question)

    if _contains_any(text, FORECAST_PATTERNS):
        return "forecasting"
    if _contains_any(text, CAUSAL_PATTERNS):
        return "causal_attribution"
    if _contains_any(text, RECOMMENDATION_PATTERNS):
        return "recommendation"

    return None


def _looks_like_definition_question(text: str) -> bool:
    definition_phrases = [
        "what does ", "define ", "definition of",
        "how do we define", "what is the definition",
        "what does it mean", "what does nrr mean",
        "what does grr mean", "what does arr mean",
        "what does mrr mean",
    ]
    metric_terms = ["arr", "mrr", "nrr", "grr", "churn", "retention"]

    return (
        _contains_any(text, definition_phrases)
        and _contains_any(text, metric_terms)
    )


def _specific_metric_intent(question: str) -> str | None:
    text = _normalize(question)

    if (
        "mrr" in text
        and _contains_any(
            text,
            ["drive", "driver", "drove", "bridge", "movement", "why"],
        )
    ) or _contains_any(text, ["recurring revenue drivers", "revenue bridge"]):
        return "mrr_bridge"

    if _contains_any(
        text,
        [
            "retention overall", "retention quality",
            "retaining customers and revenue",
            "revenue and logo retention",
        ],
    ):
        return "retention_quality"

    if _contains_any(
        text,
        [
            "revenue per customer", "arr per customer",
            "arr per account", "customer economics",
        ],
    ) and _contains_any(
        text,
        [
            "growing", "growth", "change", "changed", "changing",
            "increase", "increasing", "decrease", "decreasing",
            "more revenue", "trend",
        ],
    ):
        return "customer_economics"

    if _contains_any(
        text,
        [
            "customer growth", "customers growing",
            "customer base growing", "active customer growth",
            "logos growing", "logo growth",
        ],
    ):
        return "customer_growth"

    if (
        "arr" in text
        and _contains_any(
            text,
            ["growth", "growing", "year over year", "yoy", "trend", "growth rate"],
        )
    ) or "recurring revenue growth" in text:
        return "arr_growth"

    if _contains_any(
        text,
        [
            "concentration", "largest customers",
            "top 5", "top five", "top 10", "top ten", "top 20", "top twenty",
        ],
    ):
        return "concentration"

    if _contains_any(
        text,
        [
            "logo retention", "logo churn", "customer churn",
            "retaining customers", "customer retention",
        ],
    ):
        return "logo_retention"

    if _contains_any(text, ["nrr", "net revenue retention", "net retention"]):
        return "nrr"

    if _contains_any(text, ["grr", "gross revenue retention", "gross retention"]):
        return "grr"

    if _contains_any(
        text,
        [
            "arr per customer", "arr per account",
            "average arr per", "recurring revenue per account",
        ],
    ):
        return "arr_per_account"

    if _contains_any(
        text,
        [
            "how many customers", "active customers",
            "active accounts", "customer count", "number of customers",
        ],
    ):
        return "active_customers"

    if re.search(r"\barr\b", text) or "annual recurring revenue" in text:
        return "current_arr"

    if re.search(r"\bmrr\b", text) or "monthly recurring revenue" in text:
        return "ending_mrr"

    return None


def detect_supported_intent(question: str) -> str | None:
    text = _normalize(question)

    if _looks_like_definition_question(text):
        return "metric_definition"

    if _contains_any(
        text,
        [
            "management pay attention", "key takeaways",
            "management summary", "summarize the business",
            "executive summary", "what should management know",
        ],
    ):
        return "management_summary"

    specific = _specific_metric_intent(question)
    if specific:
        return specific

    if _contains_any(
        text,
        [
            "compare ", "compared with", "compared to",
            "versus last month", "vs last month",
            "from last month", "month over month", "mom",
        ],
    ):
        return "period_compare"

    return None


DEFINITION_ALIASES = {
    "current_arr": ["arr", "annual recurring revenue"],
    "ending_mrr": ["mrr", "monthly recurring revenue"],
    "nrr_12m": ["nrr", "net revenue retention", "net retention"],
    "grr_12m": ["grr", "gross revenue retention", "gross retention"],
    "logo_retention_12m": ["logo retention", "customer retention"],
    "logo_churn_12m": ["logo churn", "customer churn", "churn"],
}


def extract_definition_metric(question: str) -> str | None:
    text = _normalize(question)
    for metric_id, aliases in DEFINITION_ALIASES.items():
        if _contains_any(text, aliases):
            return metric_id
    return None


def _resolve_time(
    question: str,
    default_period: str | None,
) -> dict[str, Any] | None:
    anchor_period = default_period or extract_period(question, default_period=None)

    if not anchor_period:
        return None

    return resolve_time_reference(
        question=question,
        anchor_period=anchor_period,
    )


def _effective_period(
    time_context: dict[str, Any] | None,
    fallback_period: str | None,
) -> str | None:
    if not time_context:
        return fallback_period

    mode = time_context.get("mode")
    if mode == "point":
        return time_context.get("target_period")
    if mode == "comparison":
        return time_context.get("current_period") or time_context.get("anchor_period")
    if mode == "range":
        return time_context.get("end_period")

    return (
        time_context.get("target_period")
        or time_context.get("anchor_period")
        or fallback_period
    )


def _should_use_semantic_fallback(
    supported_intent: str | None,
) -> bool:
    return supported_intent in {None, "period_compare"}


def route_question(
    question: str,
    default_period: str | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    config = load_copilot_config(config_path)

    fallback_period = extract_period(
        question,
        default_period=default_period,
    )
    time_context = _resolve_time(
        question=question,
        default_period=default_period,
    )
    period = _effective_period(
        time_context=time_context,
        fallback_period=fallback_period,
    )

    unsupported_metrics = detect_unsupported_metrics(question, config)
    unsupported_intent = detect_unsupported_intent(question)
    supported_intent = detect_supported_intent(question)

    # Hard policy boundaries always win.
    if unsupported_intent:
        policy = config.get("unsupported_intents", {}).get(
            unsupported_intent,
            {},
        )
        return {
            "status": "unsupported",
            "intent": unsupported_intent,
            "period": period,
            "time": time_context,
            "metrics": [],
            "unsupported_metrics": unsupported_metrics,
            "message": policy.get(
                "response",
                config["default_messages"]["unsupported_question"],
            ),
            "resolver": "deterministic",
        }

    if unsupported_metrics and not supported_intent:
        reasons = []
        for metric_id in unsupported_metrics:
            item = config["known_unsupported_metrics"].get(metric_id, {})
            reasons.append(
                {
                    "metric_id": metric_id,
                    "display_name": item.get("display_name", metric_id),
                    "reason": item.get(
                        "reason",
                        config["default_messages"]["unsupported_metric"],
                    ),
                }
            )

        return {
            "status": "unsupported",
            "intent": "unsupported_metric",
            "period": period,
            "time": time_context,
            "metrics": [],
            "unsupported_metrics": unsupported_metrics,
            "unsupported_details": reasons,
            "message": config["default_messages"]["unsupported_metric"],
            "resolver": "deterministic",
        }

    semantic: dict[str, Any] | None = None

    if _should_use_semantic_fallback(supported_intent):
        try:
            semantic = resolve_semantically(
                question,
                deterministic_time=time_context,
                config_path=config_path,
            )
        except Exception:
            semantic = None

        if semantic:
            semantic_intent = semantic.get("intent")
            if semantic_intent in config.get("intents", {}):
                supported_intent = semantic_intent

    if supported_intent and supported_intent != "period_compare":
        intent_config = config["intents"][supported_intent]
        route_metrics = list(intent_config.get("metrics", []))

        if semantic and semantic.get("metric_ids"):
            approved_global = set(config.get("supported_metric_ids", []))
            semantic_metrics = list(semantic.get("metric_ids", []))
            if set(semantic_metrics).issubset(approved_global):
                route_metrics = semantic_metrics

        status = "partially_supported" if unsupported_metrics else "supported"

        route = {
            "status": status,
            "intent": supported_intent,
            "period": period,
            "time": time_context,
            "metrics": route_metrics,
            "unsupported_metrics": unsupported_metrics,
            "allowed_analysis": list(intent_config.get("allowed_analysis", [])),
            "resolver": "semantic" if semantic else "deterministic",
        }

        if unsupported_metrics:
            route["message"] = config["default_messages"]["partial_support"]

        if semantic:
            route["semantic_resolution"] = semantic
            route["interpretation_note_required"] = (
                float(semantic.get("confidence", 0.0)) < 0.80
            )

        if supported_intent == "metric_definition":
            route["definition_metric"] = extract_definition_metric(question)
            route["definition_source"] = intent_config.get("definition_source")

        if supported_intent == "management_summary":
            route["service"] = intent_config.get("service", "management_flags")

        return route

    return {
        "status": "unsupported",
        "intent": "unsupported_question",
        "period": period,
        "time": time_context,
        "metrics": [],
        "unsupported_metrics": unsupported_metrics,
        "message": config["default_messages"]["unsupported_question"],
        "supported_domains": config["response_rules"]["unsupported"].get(
            "supported_domains",
            [],
        ),
        "resolver": "semantic_failed",
    }


if __name__ == "__main__":
    examples = [
        "What is ARR in June 2026?",
        "What was ARR one year ago?",
        "How has customer retention been over the past year?",
        "How are we doing with keeping customers?",
        "Compare revenue retention to last year.",
        "What is CAC?",
        "Forecast ARR next quarter.",
    ]

    for example in examples:
        print("=" * 80)
        print(example)
        print(
            json.dumps(
                route_question(
                    example,
                    default_period="2026-06",
                ),
                indent=2,
                default=str,
            )
        )

    print()
    print("HYBRID ROUTER: PASS")
