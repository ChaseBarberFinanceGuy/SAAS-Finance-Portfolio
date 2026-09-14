"""
Stratum | Management Flags
Deterministic validation layer.

Generated commentary is treated as untrusted until it passes validation.

Validation covers:
- response schema
- maximum flag count
- source metrics
- selected candidate mapping
- unsupported numeric claims
- permitted presentation formatting / rounding

Important:
The LLM may FORMAT supplied facts for executive readability.
It may not CALCULATE or INVENT new facts.

Examples of permitted formatting:
    5586735.12  -> $5.6M
    465561.26   -> $465.6K
    0.5019046   -> 50.2%
    1.1529564   -> 115.3%
    -0.1627     -> -0.2 ppt

Compact notation and rounding are presentation transformations,
not new calculations.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any


# ---------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------


class ManagementFlagValidationError(ValueError):
    """Raised when generated Management Flag commentary violates policy."""


# ---------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------


def _to_plain_dict(value: Any) -> Any:
    """
    Convert common structured-response objects into plain Python objects.
    Supports dicts, dataclasses, and Pydantic-style models.
    """

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if is_dataclass(value):
        return asdict(value)

    return value


def _get_flags(response: Any) -> list[dict[str, Any]]:
    """Extract the flags array from the structured writer response."""

    response = _to_plain_dict(response)

    if not isinstance(response, Mapping):
        raise ManagementFlagValidationError(
            "Writer response must be a mapping/object."
        )

    flags = response.get("flags")

    if flags is None:
        raise ManagementFlagValidationError(
            "Writer response is missing 'flags'."
        )

    if not isinstance(flags, list):
        raise ManagementFlagValidationError(
            "'flags' must be a list."
        )

    normalized: list[dict[str, Any]] = []

    for index, flag in enumerate(flags, start=1):
        flag = _to_plain_dict(flag)

        if not isinstance(flag, Mapping):
            raise ManagementFlagValidationError(
                f"Flag {index} must be an object."
            )

        normalized.append(dict(flag))

    return normalized


# ---------------------------------------------------------------------
# Fact packet traversal
# ---------------------------------------------------------------------


def _collect_numeric_facts(
    value: Any,
    path: str = "",
) -> list[tuple[str, float]]:
    """
    Recursively collect every finite numeric value from the certified
    fact packet.

    Booleans are deliberately excluded because bool is a subclass of int.
    """

    results: list[tuple[str, float]] = []

    value = _to_plain_dict(value)

    if isinstance(value, bool):
        return results

    if isinstance(value, (int, float)):
        numeric = float(value)

        if math.isfinite(numeric):
            results.append((path, numeric))

        return results

    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)

            results.extend(
                _collect_numeric_facts(
                    child,
                    child_path,
                )
            )

        return results

    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"

            results.extend(
                _collect_numeric_facts(
                    child,
                    child_path,
                )
            )

    return results


def _collect_fact_keys(value: Any) -> set[str]:
    """Collect all dictionary keys appearing anywhere in the fact packet."""

    keys: set[str] = set()

    value = _to_plain_dict(value)

    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_collect_fact_keys(child))

    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for child in value:
            keys.update(_collect_fact_keys(child))

    return keys


# ---------------------------------------------------------------------
# Numeric claim parsing
# ---------------------------------------------------------------------


# Matches examples including:
#   $0.5K
#   $5.6M
#   115.3%
#   -0.2 ppt
#   855
#   13,360.7
#
# Currency symbol is optional because executive prose may omit it.
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
    (?P<suffix>[KMBkmb])?
    \s*
    (?P<percent>%|pct\b|percent\b)?
    \s*
    (?P<ppt>
        ppts?\b
        |
        percentage\s+points?\b
    )?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _decimal_places(number_text: str) -> int:
    if "." not in number_text:
        return 0

    return len(number_text.split(".", 1)[1])


def _is_period_reference(
    text: str,
    match: re.Match[str],
) -> bool:
    """
    Ignore obvious period labels such as:
        12 month
        12-month
        12 months
        1 year

    These are descriptors, not claimed financial values.
    """

    following = text[match.end() : match.end() + 15].lower()

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


def _extract_numeric_claims(
    text: str,
) -> list[dict[str, Any]]:
    """Extract numeric claims from executive prose."""

    claims: list[dict[str, Any]] = []

    for match in NUMBER_PATTERN.finditer(text):

        if _is_period_reference(text, match):
            continue

        raw = match.group(0).strip()

        number_text = match.group("number").replace(",", "")

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

        display_value = value * multiplier

        percent = bool(match.group("percent"))
        ppt = bool(match.group("ppt"))

        claims.append(
            {
                "raw": raw,
                "value": value,
                "display_value": display_value,
                "suffix": suffix,
                "multiplier": multiplier,
                "percent": percent,
                "ppt": ppt,
                "decimal_places": _decimal_places(number_text),
            }
        )

    return claims


# ---------------------------------------------------------------------
# Formatting-aware numeric comparison
# ---------------------------------------------------------------------


def _rounding_tolerance(
    claim: dict[str, Any],
) -> float:
    """
    Calculate the maximum difference implied by displayed precision.

    Example:
        $0.5K

    One decimal in thousands has a display step of $100.
    Therefore any certified value within $50 of $500 may legitimately
    round to $0.5K.

        $5.6M

    One decimal in millions has a display step of $100,000.
    Tolerance = $50,000.
    """

    decimal_places = claim["decimal_places"]
    multiplier = claim["multiplier"]

    display_step = multiplier * (10 ** (-decimal_places))

    return display_step / 2 + 1e-9


def _claim_matches_fact(
    claim: dict[str, Any],
    fact_value: float,
) -> bool:
    """
    Determine whether one displayed numeric claim can be derived solely
    by formatting / rounding a certified numeric fact.
    """

    # -------------------------------------------------------------
    # Percentage-point claims
    # -------------------------------------------------------------

    if claim["ppt"]:

        claimed_ppts = claim["display_value"]

        tolerance = (
            10 ** (-claim["decimal_places"])
        ) / 2 + 1e-9

        return math.isclose(
            fact_value,
            claimed_ppts,
            abs_tol=tolerance,
            rel_tol=0.0,
        )

    # -------------------------------------------------------------
    # Percent / pct claims
    #
    # Certified ratio facts are normally stored as decimals:
    #   1.152956 -> 115.3%
    #
    # We also permit already-percentage-scaled facts in case a
    # certified metric is intentionally stored that way.
    # -------------------------------------------------------------

    if claim["percent"]:

        claimed_pct = claim["value"]

        pct_tolerance = (
            10 ** (-claim["decimal_places"])
        ) / 2 + 1e-9

        fact_as_pct = fact_value * 100

        if math.isclose(
            fact_as_pct,
            claimed_pct,
            abs_tol=pct_tolerance,
            rel_tol=0.0,
        ):
            return True

        if math.isclose(
            fact_value,
            claimed_pct,
            abs_tol=pct_tolerance,
            rel_tol=0.0,
        ):
            return True

        return False

    # -------------------------------------------------------------
    # Currency / compact notation / ordinary numbers
    # -------------------------------------------------------------

    tolerance = _rounding_tolerance(claim)

    return math.isclose(
        fact_value,
        claim["display_value"],
        abs_tol=tolerance,
        rel_tol=0.0,
    )


def _number_is_supported(
    claim: dict[str, Any],
    numeric_facts: list[tuple[str, float]],
) -> bool:
    """Return True if any certified fact supports this displayed claim."""

    for _, fact_value in numeric_facts:
        if _claim_matches_fact(
            claim,
            fact_value,
        ):
            return True

    return False


# ---------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------


def _validate_schema(
    flags: list[dict[str, Any]],
) -> None:

    if len(flags) > 4:
        raise ManagementFlagValidationError(
            f"Response contains {len(flags)} flags; maximum is 4."
        )

    required_fields = {
        "candidate_id",
        "category",
        "severity",
        "headline",
        "detail",
        "source_metrics",
    }

    allowed_severities = {
        "positive",
        "negative",
        "mixed",
        "neutral",
    }

    for index, flag in enumerate(flags, start=1):

        missing = required_fields - set(flag)

        if missing:
            raise ManagementFlagValidationError(
                f"Flag {index} is missing required fields: "
                f"{sorted(missing)}"
            )

        if not str(flag["headline"]).strip():
            raise ManagementFlagValidationError(
                f"Flag {index} has an empty headline."
            )

        if not str(flag["detail"]).strip():
            raise ManagementFlagValidationError(
                f"Flag {index} has an empty detail."
            )

        severity = str(flag["severity"]).lower()

        if severity not in allowed_severities:
            raise ManagementFlagValidationError(
                f"Flag {index} has unsupported severity "
                f"{flag['severity']!r}."
            )

        source_metrics = flag["source_metrics"]

        if (
            not isinstance(source_metrics, list)
            or not source_metrics
        ):
            raise ManagementFlagValidationError(
                f"Flag {index} must contain at least one source metric."
            )


# ---------------------------------------------------------------------
# Candidate validation
# ---------------------------------------------------------------------


def _candidate_id(candidate: Any) -> str | None:

    candidate = _to_plain_dict(candidate)

    if isinstance(candidate, Mapping):
        return (
            candidate.get("candidate_id")
            or candidate.get("id")
        )

    return None


def _validate_candidate_mapping(
    flags: list[dict[str, Any]],
    selected_candidates: Sequence[Any],
) -> None:

    selected_ids = {
        candidate_id
        for candidate in selected_candidates
        if (candidate_id := _candidate_id(candidate))
    }

    for index, flag in enumerate(flags, start=1):

        candidate_id = flag.get("candidate_id")

        if candidate_id not in selected_ids:
            raise ManagementFlagValidationError(
                f"Flag {index} references candidate "
                f"{candidate_id!r}, which was not selected "
                f"by the deterministic materiality engine."
            )


# ---------------------------------------------------------------------
# Source-metric validation
# ---------------------------------------------------------------------


def _validate_source_metrics(
    flags: list[dict[str, Any]],
    fact_packet: Any,
    selected_candidates: Sequence[Any],
) -> None:

    known_metrics = _collect_fact_keys(fact_packet)

    # Candidate fact packets may include derived / bounded metrics that
    # are intentionally passed to the writer.
    for candidate in selected_candidates:
        candidate = _to_plain_dict(candidate)

        if isinstance(candidate, Mapping):
            known_metrics.update(
                _collect_fact_keys(candidate.get("facts", {}))
            )

            for metric in candidate.get("metric_ids", []) or []:
                known_metrics.add(str(metric))

    for index, flag in enumerate(flags, start=1):

        unknown = [
            metric
            for metric in flag["source_metrics"]
            if metric not in known_metrics
        ]

        if unknown:
            raise ManagementFlagValidationError(
                f"Flag {index} references unknown source metrics: "
                f"{unknown}"
            )


# ---------------------------------------------------------------------
# Numeric grounding validation
# ---------------------------------------------------------------------


def _validate_numbers(
    flags: list[dict[str, Any]],
    fact_packet: Any,
    selected_candidates: Sequence[Any],
) -> None:

    numeric_facts = _collect_numeric_facts(
        fact_packet
    )

    # Also include facts explicitly supplied inside selected candidates.
    # These are part of the bounded writer context and therefore valid
    # certified inputs for commentary.
    for candidate in selected_candidates:
        candidate = _to_plain_dict(candidate)

        if isinstance(candidate, Mapping):
            numeric_facts.extend(
                _collect_numeric_facts(
                    candidate.get("facts", {})
                )
            )

    for index, flag in enumerate(flags, start=1):

        text = " ".join(
            [
                str(flag.get("headline", "")),
                str(flag.get("detail", "")),
            ]
        )

        claims = _extract_numeric_claims(text)

        unsupported: list[str] = []

        for claim in claims:

            if not _number_is_supported(
                claim,
                numeric_facts,
            ):
                unsupported.append(
                    claim["raw"]
                )

        if unsupported:
            raise ManagementFlagValidationError(
                f"Flag {index} contains unsupported numbers: "
                f"{unsupported}"
            )


# ---------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------


def _validate_no_duplicate_candidates(
    flags: list[dict[str, Any]],
) -> None:

    seen: set[str] = set()

    for index, flag in enumerate(flags, start=1):

        candidate_id = str(
            flag["candidate_id"]
        )

        if candidate_id in seen:
            raise ManagementFlagValidationError(
                f"Flag {index} duplicates candidate "
                f"{candidate_id!r}."
            )

        seen.add(candidate_id)


# ---------------------------------------------------------------------
# Public validator
# ---------------------------------------------------------------------


def validate_response(
    response: Any,
    selected_candidates: Sequence[Any],
    fact_packet: Any,
) -> bool:
    """
    Validate generated Management Flag commentary.

    Returns True only when the generated response is safe to expose
    through the presentation layer.
    """

    flags = _get_flags(response)

    _validate_schema(
        flags
    )

    _validate_candidate_mapping(
        flags=flags,
        selected_candidates=selected_candidates,
    )

    _validate_source_metrics(
        flags=flags,
        fact_packet=fact_packet,
        selected_candidates=selected_candidates,
    )

    _validate_no_duplicate_candidates(
        flags
    )

    _validate_numbers(
        flags=flags,
        fact_packet=fact_packet,
        selected_candidates=selected_candidates,
    )

    return True