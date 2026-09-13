"""
Stratum | Management Flags
Generated-commentary validation layer.

LLM output is treated as untrusted until it passes:
- response schema checks
- selected-candidate mapping
- certified metric checks
- supported-number checks
- duplicate checks
- period / scope consistency
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
METRICS_CONFIG_PATH = REPO_ROOT / "config" / "metrics.json"


ALLOWED_SEVERITIES = {
    "positive",
    "negative",
    "mixed",
    "neutral",
}


class ManagementFlagValidationError(ValueError):
    """Raised when generated commentary violates the finance contract."""


# ------------------------------------------------------------
# Metric catalog
# ------------------------------------------------------------

def load_metric_catalog() -> dict[str, Any]:
    with METRICS_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_known_metric_ids(
    metric_catalog: dict[str, Any] | None = None,
) -> set[str]:
    if metric_catalog is None:
        metric_catalog = load_metric_catalog()

    return set(
        metric_catalog.get("metrics", {}).keys()
    )


# ------------------------------------------------------------
# Numeric helpers
# ------------------------------------------------------------

def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False

    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _flatten_numeric_values(
    obj: Any,
) -> list[float]:
    """
    Recursively collect numeric facts from a nested structure.
    """

    values: list[float] = []

    if isinstance(obj, dict):
        for value in obj.values():
            values.extend(
                _flatten_numeric_values(value)
            )

    elif isinstance(obj, (list, tuple)):
        for value in obj:
            values.extend(
                _flatten_numeric_values(value)
            )

    elif _is_number(obj):
        values.append(float(obj))

    return values


NUMBER_PATTERN = re.compile(
    r"""
    (?<![\w-])
    (?P<currency>\$)?
    (?P<number>
        -?
        (?:\d{1,3}(?:,\d{3})*|\d+)
        (?:\.\d+)?
    )
    (?P<suffix>[KkMmBb])?
    (?P<percent>%)
    |
    (?<![\w-])
    (?P<currency2>\$)?
    (?P<number2>
        -?
        (?:\d{1,3}(?:,\d{3})*|\d+)
        (?:\.\d+)?
    )
    (?P<suffix2>[KkMmBb])?
    (?![\w-])
    """,
    re.VERBOSE,
)


def _extract_numeric_mentions(
    text: str,
) -> list[dict[str, Any]]:
    """
    Extract human-readable numeric mentions from prose.

    Examples:
        $5.59M
        50.2%
        855
        $15.5K

    Numbers inside terms such as '12-month' are intentionally ignored.
    """

    mentions: list[dict[str, Any]] = []

    for match in NUMBER_PATTERN.finditer(text):

        currency = (
            match.group("currency")
            or match.group("currency2")
        )

        raw_number = (
            match.group("number")
            or match.group("number2")
        )

        suffix = (
            match.group("suffix")
            or match.group("suffix2")
        )

        percent = bool(match.group("percent"))

        if raw_number is None:
            continue

        numeric = float(
            raw_number.replace(",", "")
        )

        multiplier = 1.0

        if suffix:
            multiplier = {
                "k": 1_000.0,
                "m": 1_000_000.0,
                "b": 1_000_000_000.0,
            }[suffix.lower()]

        normalized = numeric * multiplier

        mentions.append(
            {
                "raw": match.group(0),
                "value": normalized,
                "percent": percent,
                "currency": bool(currency),
            }
        )

    return mentions


def _matches_fact(
    mention: dict[str, Any],
    fact_values: list[float],
) -> bool:
    """
    Determine whether a prose number is supported by supplied facts.

    Percentage facts are typically stored as decimals, so 50.2%
    is compared against both 50.2 and 0.502-style representations.
    """

    stated = float(mention["value"])

    for fact in fact_values:

        comparisons = [fact]

        if mention["percent"]:
            comparisons.append(fact * 100.0)

        for comparison in comparisons:

            # Currency / compact figures need rounding tolerance.
            if mention["currency"]:
                tolerance = max(
                    1.0,
                    abs(stated) * 0.01,
                )

            # Percentage prose commonly rounds to one decimal place.
            elif mention["percent"]:
                tolerance = 0.15

            else:
                tolerance = max(
                    0.5,
                    abs(stated) * 0.005,
                )

            if abs(stated - comparison) <= tolerance:
                return True

    return False


# ------------------------------------------------------------
# Validation
# ------------------------------------------------------------

def validate_response(
    response: dict[str, Any],
    selected_candidates: list[dict[str, Any]],
    fact_packet: dict[str, Any],
    metric_catalog: dict[str, Any] | None = None,
    max_flags: int = 4,
) -> bool:
    """
    Validate generated Management Flags.

    Returns True only when every control passes.
    Raises ManagementFlagValidationError on failure.
    """

    if metric_catalog is None:
        metric_catalog = load_metric_catalog()

    # --------------------------------------------------------
    # Basic response structure
    # --------------------------------------------------------

    if not isinstance(response, dict):
        raise ManagementFlagValidationError(
            "LLM response must be a dictionary."
        )

    flags = response.get("flags")

    if not isinstance(flags, list):
        raise ManagementFlagValidationError(
            "Response must contain a 'flags' list."
        )

    if len(flags) > max_flags:
        raise ManagementFlagValidationError(
            f"Response contains {len(flags)} flags; "
            f"maximum allowed is {max_flags}."
        )

    # Zero flags is valid.
    if not flags:
        return True

    # --------------------------------------------------------
    # Period / scope
    # --------------------------------------------------------

    expected_period = fact_packet.get("period")

    if response.get("as_of_month") != expected_period:
        raise ManagementFlagValidationError(
            "Response period does not match the finance snapshot."
        )

    expected_scope = fact_packet.get("scope", {})

    if response.get("scope") != expected_scope:
        raise ManagementFlagValidationError(
            "Response scope does not match the finance snapshot."
        )

    # --------------------------------------------------------
    # Candidate lookup
    # --------------------------------------------------------

    selected_by_id = {
        candidate["id"]: candidate
        for candidate in selected_candidates
    }

    known_metric_ids = get_known_metric_ids(
        metric_catalog
    )

    seen_candidate_ids: set[str] = set()

    # --------------------------------------------------------
    # Validate each flag
    # --------------------------------------------------------

    for index, flag in enumerate(flags, start=1):

        if not isinstance(flag, dict):
            raise ManagementFlagValidationError(
                f"Flag {index} is not an object."
            )

        required_fields = {
            "candidate_id",
            "category",
            "severity",
            "headline",
            "detail",
            "source_metrics",
        }

        missing = required_fields - set(flag.keys())

        if missing:
            raise ManagementFlagValidationError(
                f"Flag {index} missing fields: "
                f"{sorted(missing)}"
            )

        candidate_id = flag["candidate_id"]

        if candidate_id not in selected_by_id:
            raise ManagementFlagValidationError(
                f"Flag {index} references unselected "
                f"candidate '{candidate_id}'."
            )

        if candidate_id in seen_candidate_ids:
            raise ManagementFlagValidationError(
                f"Candidate '{candidate_id}' appears more than once."
            )

        seen_candidate_ids.add(candidate_id)

        candidate = selected_by_id[candidate_id]

        # ----------------------------------------------------
        # Category / severity
        # ----------------------------------------------------

        if flag["category"] != candidate["category"]:
            raise ManagementFlagValidationError(
                f"Flag {index} category does not match "
                f"candidate '{candidate_id}'."
            )

        if flag["severity"] not in ALLOWED_SEVERITIES:
            raise ManagementFlagValidationError(
                f"Flag {index} has invalid severity "
                f"'{flag['severity']}'."
            )

        # ----------------------------------------------------
        # Text requirements
        # ----------------------------------------------------

        headline = flag["headline"]
        detail = flag["detail"]

        if not isinstance(headline, str) or not headline.strip():
            raise ManagementFlagValidationError(
                f"Flag {index} has an empty headline."
            )

        if not isinstance(detail, str) or not detail.strip():
            raise ManagementFlagValidationError(
                f"Flag {index} has an empty detail."
            )

        if len(headline) > 180:
            raise ManagementFlagValidationError(
                f"Flag {index} headline is too long."
            )

        if len(detail) > 350:
            raise ManagementFlagValidationError(
                f"Flag {index} detail is too long."
            )

        # ----------------------------------------------------
        # Source metrics
        # ----------------------------------------------------

        source_metrics = flag["source_metrics"]

        if (
            not isinstance(source_metrics, list)
            or not source_metrics
        ):
            raise ManagementFlagValidationError(
                f"Flag {index} must cite at least one metric."
            )

        unknown_metrics = (
            set(source_metrics)
            - known_metric_ids
        )

        if unknown_metrics:
            raise ManagementFlagValidationError(
                f"Flag {index} cites unknown metrics: "
                f"{sorted(unknown_metrics)}"
            )

        allowed_for_candidate = set(
            candidate.get("metric_ids", [])
        )

        unsupported_sources = (
            set(source_metrics)
            - allowed_for_candidate
        )

        if unsupported_sources:
            raise ManagementFlagValidationError(
                f"Flag {index} cites metrics not approved for "
                f"candidate '{candidate_id}': "
                f"{sorted(unsupported_sources)}"
            )

        # ----------------------------------------------------
        # Numeric grounding
        # ----------------------------------------------------

        fact_values = _flatten_numeric_values(
            candidate.get("facts", {})
        )

        prose = f"{headline} {detail}"

        numeric_mentions = _extract_numeric_mentions(
            prose
        )

        unsupported_numbers = []

        for mention in numeric_mentions:
            if not _matches_fact(
                mention,
                fact_values,
            ):
                unsupported_numbers.append(
                    mention["raw"]
                )

        if unsupported_numbers:
            raise ManagementFlagValidationError(
                f"Flag {index} contains unsupported numbers: "
                f"{unsupported_numbers}"
            )

        # ----------------------------------------------------
        # Weak / generic language checks
        # ----------------------------------------------------

        lower_prose = prose.lower()

        banned_phrases = [
            "strong performance",
            "excellent performance",
            "great performance",
            "very strong",
            "doing well",
        ]

        for phrase in banned_phrases:
            if phrase in lower_prose:
                raise ManagementFlagValidationError(
                    f"Flag {index} contains unsupported generic "
                    f"language: '{phrase}'."
                )

    return True


# ------------------------------------------------------------
# Smoke-test helper
# ------------------------------------------------------------

if __name__ == "__main__":

    print(
        "validator.py loaded successfully."
    )