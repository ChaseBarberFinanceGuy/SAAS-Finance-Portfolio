"""Materiality scoring, deduplication, and selection."""
from __future__ import annotations
from collections.abc import Iterable
from .candidate_rules import Candidate

def dedupe(candidates: Iterable[Candidate]) -> list[Candidate]:
    best = {}
    for candidate in candidates:
        key = candidate.family or candidate.id
        if key not in best or candidate.score > best[key].score:
            best[key] = candidate
    return list(best.values())

def rank_and_select(candidates: Iterable[Candidate], *, minimum_score: float, max_flags: int = 4) -> list[Candidate]:
    eligible = [c for c in candidates if c.score >= minimum_score]
    eligible = dedupe(eligible)
    eligible.sort(key=lambda c: c.score, reverse=True)
    return eligible[:min(max_flags, 4)]
