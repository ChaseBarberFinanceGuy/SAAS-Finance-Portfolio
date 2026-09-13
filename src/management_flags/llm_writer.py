"""Provider-agnostic LLM writer."""
from __future__ import annotations
from typing import Any, Protocol

class LLMProvider(Protocol):
    def generate_json(self, *, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]: ...

def build_writer_payload(*, period: str, scope: dict[str, Any], selected_candidates: list[dict[str, Any]],
                         metric_definitions: dict[str, Any], writing_rules: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "period": period,
        "scope": scope,
        "candidates": selected_candidates,
        "metric_definitions": metric_definitions,
        "writing_rules": writing_rules or {},
    }

def write_flags(*, provider: LLMProvider, payload: dict[str, Any], max_flags: int = 4) -> dict[str, Any]:
    system_prompt = f"""You are the executive finance commentary writer for Stratum.
Use only supplied facts. Do not calculate unsupported numbers.
Return zero to {min(max_flags,4)} material, non-duplicative management flags.
Never add a flag merely to reach a count. If candidates are empty, return {{"flags":[]}}."""
    return provider.generate_json(system_prompt=system_prompt, payload=payload)
