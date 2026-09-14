"""
Stratum | Management Flags
Service layer.

Provides one clean entry point for the application:

    get_management_flags("2026-06")

Pipeline:
certified metrics
    -> finance snapshot
    -> deterministic candidates
    -> materiality selection
    -> LLM commentary
    -> validation
"""

from __future__ import annotations

from typing import Any

from src.management_flags.snapshot import build_finance_snapshot
from src.management_flags.candidate_rules import generate_candidates
from src.management_flags.materiality import rank_and_select
from src.management_flags.llm_writer import write_flags
from src.management_flags.validator import validate_response


def get_management_flags(
    as_of_month: str,
) -> dict[str, Any]:
    """
    Generate validated Management Flags for a reporting month.

    The returned payload is safe for the presentation layer only
    after it passes the deterministic validator.
    """

    # 1. Build bounded certified finance snapshot.
    snapshot = build_finance_snapshot(
        as_of_month
    )

    # 2. Generate deterministic candidate observations.
    candidates = generate_candidates(
        snapshot
    )

    # 3. Score, merge, deduplicate, and select material stories.
    selected = rank_and_select(
        candidates
    )

    # 4. Convert selected stories into executive commentary.
    response = write_flags(
        selected_candidates=selected,
        snapshot=snapshot,
    )

    # 5. Validate LLM output against certified facts.
    validate_response(
        response=response,
        selected_candidates=selected,
        fact_packet=snapshot,
    )

    return response


if __name__ == "__main__":

    import json

    result = get_management_flags(
        "2026-06"
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )

    print()
    print("SERVICE PIPELINE: PASS")