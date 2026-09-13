"""Deterministic candidate generation."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Candidate:
    id: str
    category: str
    direction: str
    metric_ids: list[str]
    facts: dict[str, Any]
    score: float = 0.0
    rationale: str = ""
    family: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

def generate_candidates(snapshot: dict[str, Any], config: dict[str, Any]) -> list[Candidate]:
    raise NotImplementedError(
        "Milestone 1: implement ARR growth, MRR bridge, NRR, GRR, "
        "active-customer, ARR/account, and concentration rules."
    )
