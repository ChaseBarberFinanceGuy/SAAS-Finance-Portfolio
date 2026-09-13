"""
Stratum | Management Flags
Constrained LLM executive-commentary writer.

The model receives only:
- selected deterministic candidates
- approved candidate facts
- approved metric IDs
- reporting period and scope

It is not allowed to calculate finance metrics or inspect raw data.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI


DEFAULT_MODEL = os.getenv(
    "STRATUM_LLM_MODEL",
    "gpt-5.6-luna",
)


SYSTEM_INSTRUCTIONS = """
You are the executive finance commentary writer for Stratum,
a synthetic B2B SaaS company used in a strategic-finance portfolio.

You do not calculate finance metrics.

You may use ONLY the candidate facts supplied to you.
Do not infer, derive, estimate, extrapolate, or invent numerical values.

Your job is to convert already-selected deterministic finance stories
into concise executive management flags.

Rules:

1. Return zero to four flags.
2. Never add a flag merely to reach a target count.
3. Write exactly one flag per supplied selected candidate unless the
   candidate clearly cannot support useful commentary.
4. Preserve the supplied candidate_id exactly.
5. Preserve the supplied category exactly.
6. source_metrics must contain only metric IDs supplied for that candidate.
7. You may format supplied numeric facts for executive readability,
   but you may not calculate new facts.

   Presentation formatting is allowed:
   - Ratio/rate values stored as decimals may be shown as percentages.
     Example: 1.152956 may be written as 115.3%.
   - Percentages should normally use one decimal place.
   - Currency should normally use commas or compact notation.
     Example: 5586735.12 may be written as $5.6M.
   - Counts should normally be shown as whole numbers with commas.
   - Percentage-point changes should normally use one decimal place
     and the label "ppt" or "percentage points".
   - Do not expose unnecessary raw decimal precision.

8. Do not calculate new percentages, deltas, ratios, totals, averages,
   causes, or forecasts. Rounding and display-unit conversion are
   presentation formatting, not new calculations.
9. Do not claim causality unless explicitly supported by the facts.
10. Do not make recommendations unless the supplied candidate explicitly
    supports one.
11. Avoid filler such as "strong performance", "excellent results",
    "doing well", or generic praise.
12. Headline should be one concise management takeaway.
13. Detail should be one sentence explaining the supporting facts or
    management implication.
14. Use executive finance language rather than promotional language.
15. When signals conflict, describe the tension instead of forcing a
    positive or negative conclusion.

Severity must be one of:
- positive
- negative
- mixed
- neutral

Return ONLY valid JSON.

Required response schema:

{
  "as_of_month": "YYYY-MM",
  "scope": {},
  "flags": [
    {
      "candidate_id": "exact supplied candidate id",
      "category": "exact supplied category",
      "severity": "positive | negative | mixed | neutral",
      "headline": "concise executive takeaway",
      "detail": "one supporting sentence",
      "source_metrics": ["approved_metric_id"]
    }
  ]
}
"""


# ------------------------------------------------------------
# Prompt construction
# ------------------------------------------------------------

def build_writer_packet(
    selected_candidates: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the bounded evidence packet supplied to the LLM.

    Scores and internal ranking rationale are included for context,
    but raw tables and unrestricted database access are not.
    """

    candidates = []

    for candidate in selected_candidates:

        candidates.append(
            {
                "candidate_id": candidate["id"],
                "category": candidate["category"],
                "direction": candidate.get(
                    "direction"
                ),
                "score": candidate.get(
                    "score"
                ),
                "approved_metric_ids": candidate.get(
                    "metric_ids",
                    [],
                ),
                "facts": candidate.get(
                    "facts",
                    {},
                ),
                "selection_rationale": candidate.get(
                    "rationale"
                ),
                "merged_from": candidate.get(
                    "merged_from",
                    [],
                ),
            }
        )

    return {
        "period": snapshot["period"],
        "scope": snapshot.get(
            "scope",
            {},
        ),
        "selected_candidates": candidates,
    }


def _parse_json_response(
    text: str,
) -> dict[str, Any]:
    """
    Parse JSON, tolerating accidental markdown fences.
    """

    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    try:
        return json.loads(text)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "LLM returned invalid JSON."
        ) from exc


# ------------------------------------------------------------
# Writer
# ------------------------------------------------------------

def write_flags(
    selected_candidates: list[dict[str, Any]],
    snapshot: dict[str, Any],
    model: str | None = None,
) -> dict[str, Any]:
    """
    Generate structured executive commentary.

    If no candidates were selected, no LLM call is made.
    """

    if not selected_candidates:
        return {
            "as_of_month": snapshot["period"],
            "scope": snapshot.get(
                "scope",
                {},
            ),
            "flags": [],
        }

    model = model or DEFAULT_MODEL

    packet = build_writer_packet(
        selected_candidates,
        snapshot,
    )

    client = OpenAI()

    response = client.responses.create(
        model=model,
        instructions=SYSTEM_INSTRUCTIONS,
        input=(
            "Write Stratum Management Flags using only "
            "the following certified evidence packet.\n\n"
            + json.dumps(
                packet,
                indent=2,
                default=str,
            )
        ),
    )

    raw_text = response.output_text

    result = _parse_json_response(
        raw_text
    )

    return result


# ------------------------------------------------------------
# Local smoke test
# ------------------------------------------------------------

if __name__ == "__main__":

    from src.management_flags.snapshot import (
        build_finance_snapshot,
    )
    from src.management_flags.candidate_rules import (
        generate_candidates,
    )
    from src.management_flags.materiality import (
        rank_and_select,
    )
    from src.management_flags.validator import (
        validate_response,
    )

    snapshot = build_finance_snapshot(
        "2026-06"
    )

    candidates = generate_candidates(
        snapshot
    )

    selected = rank_and_select(
        candidates
    )

    response = write_flags(
        selected,
        snapshot,
    )

    validate_response(
        response=response,
        selected_candidates=selected,
        fact_packet=snapshot,
    )

    print(
        json.dumps(
            response,
            indent=2,
            default=str,
        )
    )

    print()
    print("VALIDATION: PASS")