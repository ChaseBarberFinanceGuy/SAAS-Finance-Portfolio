"""
Stratum | Finance Copilot
Deterministic temporal resolver.

Relative dates are anchored to the selected reporting month, not today's date.

Examples with anchor_period="2026-06":
- "one year ago" -> 2025-06
- "6 months ago" -> 2025-12
- "last month" -> 2026-05
- "past 6 months" -> 2026-01 through 2026-06
- "past 12 months" -> 2025-07 through 2026-06
- "compare to a year ago" -> 2025-06 vs 2026-06

Important:
"What is 12-month NRR?" is a point-in-time trailing metric request, NOT a
request for a 12-month time series.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Literal

TemporalMode = Literal["anchor", "point", "range", "comparison"]

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


@dataclass(frozen=True)
class TemporalResolution:
    mode: TemporalMode
    anchor_period: str
    target_period: str | None = None
    start_period: str | None = None
    end_period: str | None = None
    periods: list[str] | None = None
    comparison_period: str | None = None
    current_period: str | None = None
    explicit_periods: list[str] | None = None
    matched_phrase: str | None = None
    range_months: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _validate_period(period: str) -> str:
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", period):
        raise ValueError(
            f"Invalid reporting period {period!r}; expected YYYY-MM."
        )
    return period


def shift_month(period: str, months: int) -> str:
    _validate_period(period)
    year, month = map(int, period.split("-"))
    index = year * 12 + (month - 1) + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_range(start_period: str, end_period: str) -> list[str]:
    _validate_period(start_period)
    _validate_period(end_period)

    start_y, start_m = map(int, start_period.split("-"))
    end_y, end_m = map(int, end_period.split("-"))

    if (end_y, end_m) < (start_y, start_m):
        raise ValueError("End period precedes start period.")

    result = []
    current = start_period

    while True:
        result.append(current)
        if current == end_period:
            break
        current = shift_month(current, 1)

    return result


def extract_explicit_periods(question: str) -> list[str]:
    text = question.lower()
    found: list[tuple[int, str]] = []

    for match in re.finditer(
        r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b",
        text,
    ):
        found.append(
            (
                match.start(),
                f"{int(match.group(1)):04d}-{int(match.group(2)):02d}",
            )
        )

    month_pattern = "|".join(
        sorted(MONTH_LOOKUP, key=len, reverse=True)
    )

    for match in re.finditer(
        rf"\b({month_pattern})\s+(20\d{{2}})\b",
        text,
    ):
        found.append(
            (
                match.start(),
                f"{int(match.group(2)):04d}-{MONTH_LOOKUP[match.group(1)]:02d}",
            )
        )

    found.sort(key=lambda item: item[0])

    periods = []
    for _, period in found:
        if period not in periods:
            periods.append(period)

    return periods


def _is_comparison_language(text: str) -> bool:
    return bool(
        re.search(
            r"\b(compare|compared|versus|vs\.?|difference|changed|change|"
            r"increase|decrease|since|from)\b",
            text,
        )
    )


def _is_range_language(text: str) -> bool:
    return bool(
        re.search(
            r"\b(over\s+(?:the\s+)?(?:past|last)|during\s+the\s+(?:past|last)|"
            r"for\s+the\s+(?:past|last)|past|last|trend\s+over|history\s+over)\b",
            text,
        )
    )


def _relative_months_ago(text: str) -> tuple[int, str] | None:
    fixed = [
        (r"\b(?:one|1|a)\s+year\s+ago\b", 12),
        (r"\b(?:one|1)\s+month\s+ago\b", 1),
        (r"\blast\s+month\b", 1),
        (r"\blast\s+year\b", 12),
        (r"\bprior\s+year\b", 12),
        (r"\bprevious\s+year\b", 12),
    ]

    for pattern, months in fixed:
        match = re.search(pattern, text)
        if match:
            return months, match.group(0)

    match = re.search(r"\b(\d+)\s+months?\s+ago\b", text)
    if match:
        return int(match.group(1)), match.group(0)

    match = re.search(r"\b(\d+)\s+years?\s+ago\b", text)
    if match:
        return int(match.group(1)) * 12, match.group(0)

    return None


def _range_length_months(text: str) -> tuple[int, str] | None:
    match = re.search(
        r"\b(?:past|last)\s+(\d+)\s+months?\b",
        text,
    )
    if match:
        return int(match.group(1)), match.group(0)

    match = re.search(
        r"\b(?:past|last)\s+(\d+)\s+years?\b",
        text,
    )
    if match:
        return int(match.group(1)) * 12, match.group(0)

    match = re.search(
        r"\b(?:past|last)\s+(?:one|1)?\s*year\b",
        text,
    )
    if match:
        return 12, match.group(0)

    return None


def resolve_time_reference(
    question: str,
    anchor_period: str,
) -> dict:
    """
    Resolve temporal language into an explicit month, month range, or comparison.
    """

    anchor_period = _validate_period(anchor_period)
    text = question.lower().strip()
    explicit = extract_explicit_periods(question)

    # Two explicit periods: compare June 2025 to June 2026
    if len(explicit) >= 2 and _is_comparison_language(text):
        return TemporalResolution(
            mode="comparison",
            anchor_period=anchor_period,
            comparison_period=explicit[0],
            current_period=explicit[1],
            explicit_periods=explicit[:2],
            matched_phrase="explicit period comparison",
        ).to_dict()

    # One explicit period
    if len(explicit) == 1:
        period = explicit[0]

        if _is_comparison_language(text):
            return TemporalResolution(
                mode="comparison",
                anchor_period=anchor_period,
                comparison_period=period,
                current_period=anchor_period,
                explicit_periods=explicit,
                matched_phrase="explicit period vs anchor",
            ).to_dict()

        return TemporalResolution(
            mode="point",
            anchor_period=anchor_period,
            target_period=period,
            explicit_periods=explicit,
            matched_phrase="explicit period",
        ).to_dict()

    # Relative range: "over the past 6 months"
    if _is_range_language(text):
        range_match = _range_length_months(text)

        if range_match:
            months, phrase = range_match

            if months < 1:
                raise ValueError("Range must contain at least one month.")

            start = shift_month(anchor_period, -(months - 1))

            return TemporalResolution(
                mode="range",
                anchor_period=anchor_period,
                start_period=start,
                end_period=anchor_period,
                periods=month_range(start, anchor_period),
                explicit_periods=[],
                matched_phrase=phrase,
                range_months=months,
            ).to_dict()

    # Relative point or comparison: "6 months ago", "since one year ago"
    relative = _relative_months_ago(text)

    if relative:
        months_ago, phrase = relative
        target = shift_month(anchor_period, -months_ago)

        if _is_comparison_language(text):
            return TemporalResolution(
                mode="comparison",
                anchor_period=anchor_period,
                comparison_period=target,
                current_period=anchor_period,
                explicit_periods=[],
                matched_phrase=phrase,
            ).to_dict()

        return TemporalResolution(
            mode="point",
            anchor_period=anchor_period,
            target_period=target,
            explicit_periods=[],
            matched_phrase=phrase,
        ).to_dict()

    # No temporal language
    return TemporalResolution(
        mode="anchor",
        anchor_period=anchor_period,
        target_period=anchor_period,
        explicit_periods=[],
    ).to_dict()


if __name__ == "__main__":
    anchor = "2026-06"

    examples = [
        "What is ARR?",
        "What was ARR in June 2025?",
        "What was ARR one year ago?",
        "What was ARR 6 months ago?",
        "What was NRR last month?",
        "Show ARR over the past 6 months",
        "Show ARR over the past 12 months",
        "How has ARR changed since one year ago?",
        "Compare ARR to 6 months ago",
        "Compare June 2025 to June 2026 ARR",
        "What is 12-month NRR?",
        "How has 12-month NRR changed over the past 12 months?",
    ]

    for question in examples:
        print("=" * 80)
        print(question)
        print(
            json.dumps(
                resolve_time_reference(
                    question=question,
                    anchor_period=anchor,
                ),
                indent=2,
            )
        )

    print()
    print("TIME RESOLVER: PASS")
