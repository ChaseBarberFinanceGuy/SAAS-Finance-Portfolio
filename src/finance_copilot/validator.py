"""
Stratum | Finance Copilot
Deterministic response validator with temporal grounding.

The writer is treated as untrusted. This validator checks:
- response schema,
- status consistency,
- source-metric boundaries,
- numeric grounding with executive-formatting tolerance,
- temporal range/comparison grounding,
- unsupported/partial-support disclosure.

The validator does not calculate finance metrics.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


class FinanceCopilotValidationError(ValueError):
    """Raised when a generated Finance Copilot response is not grounded."""


NUMBER_PATTERN = re.compile(
    r"""
    (?<![\w])
    (?P<currency>\$)?
    (?P<sign>[+-])?
    (?P<number>
        (?:\d{1,3}(?:,\d{3})+|\d+)
        (?:\.\d+)?
    )
    \s*
    (?:
        (?P<suffix>[KMBkmb])
        (?![A-Za-z])
    )?
    \s*
    (?P<percent>%|pct\b|percent\b)?
    \s*
    (?P<ppt>ppts?\b|percentage\s+points?\b)?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _collect_numeric_facts(value: Any) -> list[float]:
    values: list[float] = []

    if isinstance(value, bool):
        return values

    if isinstance(value, (int, float)):
        numeric = float(value)
        if math.isfinite(numeric):
            values.append(numeric)
        return values

    if isinstance(value, Mapping):
        for child in value.values():
            values.extend(_collect_numeric_facts(child))

    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for child in value:
            values.extend(_collect_numeric_facts(child))

    return values


def _decimal_places(text: str) -> int:
    return len(text.split(".", 1)[1]) if "." in text else 0


def _is_period_reference(
    text: str,
    match: re.Match[str],
) -> bool:
    """
    Ignore obvious date/window labels such as:
    12 month, 12-month, 12 months, 12M, 1 year.
    """

    raw = match.group(0).strip().lower()

    if raw == "12m":
        return True

    following = text[match.end() : match.end() + 24].lower()

    return bool(
        re.match(
            r"""
            ^\s*-?\s*
            (
                months?
                |
                years?
                |
                quarters?
            )\b
            """,
            following,
            re.VERBOSE,
        )
    )


def _extract_claims(text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []

    for match in NUMBER_PATTERN.finditer(text):
        if _is_period_reference(text, match):
            continue

        raw = match.group(0).strip()
        number_text = match.group("number").replace(",", "")

        # Reporting years are context, not financial claims.
        if (
            not match.group("currency")
            and not match.group("suffix")
            and not match.group("percent")
            and not match.group("ppt")
        ):
            try:
                plain_number = int(match.group("number").replace(",", ""))
            except ValueError:
                plain_number = None

            if plain_number is not None and 2000 <= plain_number <= 2100:
                continue

        try:
            value = float(number_text)
        except ValueError:
            continue

        if match.group("sign") == "-":
            value *= -1

        suffix = (
            match.group("suffix").upper()
            if match.group("suffix")
            else None
        )

        multiplier = {
            None: 1.0,
            "K": 1_000.0,
            "M": 1_000_000.0,
            "B": 1_000_000_000.0,
        }[suffix]

        claims.append(
            {
                "raw": raw,
                "value": value,
                "display_value": value * multiplier,
                "multiplier": multiplier,
                "percent": bool(match.group("percent")),
                "ppt": bool(match.group("ppt")),
                "decimal_places": _decimal_places(number_text),
            }
        )

    return claims


def _claim_matches_fact(
    claim: dict[str, Any],
    fact: float,
) -> bool:
    decimals = claim["decimal_places"]

    if claim["percent"]:
        tolerance = (10 ** (-decimals)) / 2 + 1e-9

        return (
            math.isclose(
                fact * 100,
                claim["value"],
                abs_tol=tolerance,
                rel_tol=0.0,
            )
            or math.isclose(
                fact,
                claim["value"],
                abs_tol=tolerance,
                rel_tol=0.0,
            )
        )

    if claim["ppt"]:
        tolerance = (10 ** (-decimals)) / 2 + 1e-9

        return (
            math.isclose(
                fact,
                claim["display_value"],
                abs_tol=tolerance,
                rel_tol=0.0,
            )
            or math.isclose(
                fact * 100,
                claim["value"],
                abs_tol=tolerance,
                rel_tol=0.0,
            )
        )

    display_step = claim["multiplier"] * (10 ** (-decimals))
    tolerance = display_step / 2 + 1e-9

    return math.isclose(
        fact,
        claim["display_value"],
        abs_tol=tolerance,
        rel_tol=0.0,
    )


def _validate_schema(response: dict[str, Any]) -> None:
    required = {
        "answer",
        "source_metrics",
        "status",
    }

    missing = required - set(response)

    if missing:
        raise FinanceCopilotValidationError(
            f"Response is missing fields: {sorted(missing)}"
        )

    if not isinstance(response["answer"], str):
        raise FinanceCopilotValidationError(
            "'answer' must be a string."
        )

    if not isinstance(response["source_metrics"], list):
        raise FinanceCopilotValidationError(
            "'source_metrics' must be a list."
        )

    if response["status"] not in {
        "supported",
        "partially_supported",
        "unsupported",
    }:
        raise FinanceCopilotValidationError(
            f"Invalid status: {response['status']!r}"
        )


def _validate_status(
    response: dict[str, Any],
    route: dict[str, Any],
) -> None:
    expected = route.get("status")

    if response["status"] != expected:
        raise FinanceCopilotValidationError(
            f"Route status {expected!r} returned "
            f"response status {response['status']!r}."
        )


def _validate_source_metrics(
    response: dict[str, Any],
    route: dict[str, Any],
    context: dict[str, Any],
) -> None:
    used = {
        str(metric)
        for metric in response.get("source_metrics", [])
    }

    allowed = {
        str(metric)
        for metric in route.get("metrics", [])
    }

    allowed.update(
        str(metric)
        for metric in context.get("definitions", {}).keys()
    )

    unknown = used - allowed

    if unknown:
        raise FinanceCopilotValidationError(
            "Response cites metrics outside the approved route: "
            + ", ".join(sorted(unknown))
        )


def _numeric_grounding_packet(
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    All deterministic/certified numeric structures the writer may reference.

    Temporal upgrade:
    - comparison facts + deltas are valid grounding
    - range series + endpoint deltas are valid grounding
    """

    return {
        "facts": context.get("facts", {}),
        "management_flags": context.get("management_flags", {}),
        "comparison": context.get("comparison", {}),
        "range": context.get("range", {}),
    }


def _validate_numbers(
    response: dict[str, Any],
    context: dict[str, Any],
) -> None:
    numeric_facts = _collect_numeric_facts(
        _numeric_grounding_packet(context)
    )

    claims = _extract_claims(response["answer"])
    unsupported: list[str] = []

    for claim in claims:
        if not any(
            _claim_matches_fact(claim, fact)
            for fact in numeric_facts
        ):
            unsupported.append(claim["raw"])

    if unsupported:
        raise FinanceCopilotValidationError(
            "Answer contains unsupported numbers: "
            + repr(unsupported)
        )


def _validate_partial_disclosure(
    response: dict[str, Any],
    route: dict[str, Any],
) -> None:
    if route.get("status") != "partially_supported":
        return

    unsupported = route.get("unsupported_metrics", [])

    if not unsupported:
        return

    answer = response["answer"].lower()

    disclosure_words = (
        "not currently",
        "not tracked",
        "unsupported",
        "not available",
        "can't",
        "cannot",
    )

    if not any(word in answer for word in disclosure_words):
        raise FinanceCopilotValidationError(
            "Partially supported answer did not disclose "
            "the unsupported portion."
        )


def validate_copilot_answer(
    response: dict[str, Any],
    route: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """Validate a Finance Copilot answer before presentation."""

    if not isinstance(response, Mapping):
        raise FinanceCopilotValidationError(
            "Finance Copilot response must be an object."
        )

    response = dict(response)

    _validate_schema(response)
    _validate_status(response, route)
    _validate_source_metrics(
        response=response,
        route=route,
        context=context,
    )
    _validate_numbers(
        response=response,
        context=context,
    )
    _validate_partial_disclosure(
        response=response,
        route=route,
    )

    return True


if __name__ == "__main__":
    route = {
        "status": "supported",
        "intent": "arr_growth",
        "period": "2026-06",
        "metrics": [
            "current_arr",
            "arr_yoy_growth_pct",
        ],
    }

    point_context = {
        "facts": {
            "current_arr": 5_586_735.12,
            "arr_yoy_growth_pct": 0.5019046032,
        }
    }

    good = {
        "answer": "ARR was $5.6M, up 50.2% year over year.",
        "source_metrics": [
            "current_arr",
            "arr_yoy_growth_pct",
        ],
        "status": "supported",
    }

    validate_copilot_answer(
        response=good,
        route=route,
        context=point_context,
    )
    print("VALIDATOR POINT CASE: PASS")

    bad = {
        "answer": "ARR was $9.9M, up 50.2% year over year.",
        "source_metrics": [
            "current_arr",
            "arr_yoy_growth_pct",
        ],
        "status": "supported",
    }

    try:
        validate_copilot_answer(
            response=bad,
            route=route,
            context=point_context,
        )
    except FinanceCopilotValidationError:
        print("VALIDATOR HALLUCINATION CASE: PASS")
    else:
        raise AssertionError(
            "Validator failed to reject an unsupported number."
        )

    temporal_route = {
        "status": "supported",
        "intent": "logo_retention",
        "period": "2026-06",
        "metrics": [
            "logo_retention_12m",
            "logo_churn_12m",
        ],
    }

    temporal_context = {
        "facts": {
            "logo_retention_12m": 0.826687,
            "logo_churn_12m": 0.173313,
        },
        "range": {
            "series": [
                {
                    "period": "2025-07",
                    "facts": {
                        "logo_retention_12m": 0.8000,
                        "logo_churn_12m": 0.2000,
                    },
                },
                {
                    "period": "2026-06",
                    "facts": {
                        "logo_retention_12m": 0.826687,
                        "logo_churn_12m": 0.173313,
                    },
                },
            ],
            "deltas": {
                "logo_retention_12m": {
                    "absolute_change": 0.026687,
                    "percent_change": 0.03335875,
                }
            },
        },
    }

    temporal_good = {
        "answer": (
            "12-month customer retention increased from 80.0% "
            "to 82.7% over the period."
        ),
        "source_metrics": [
            "logo_retention_12m",
        ],
        "status": "supported",
    }

    validate_copilot_answer(
        response=temporal_good,
        route=temporal_route,
        context=temporal_context,
    )
    print("VALIDATOR TEMPORAL RANGE CASE: PASS")
