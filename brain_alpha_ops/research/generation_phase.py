"""Candidate generation phase service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from brain_alpha_ops.models import Candidate


AssistantGuidanceApplier = Callable[[Candidate, dict[str, Any]], None]


@dataclass
class GenerationPhaseService:
    """Merge generator output with assistant/research-memory/plugin metadata."""

    generator: Any
    max_candidates: int
    dataset_id: str = ""
    attach_assistant_guidance: AssistantGuidanceApplier | None = None

    def generate(self, *, assistant_guidance: dict[str, Any] | None = None) -> list[Candidate]:
        candidates = list(
            self.generator.generate(
                self.max_candidates,
                dataset_id=self.dataset_id,
            )
        )
        if assistant_guidance and self.attach_assistant_guidance:
            for candidate in candidates:
                self.attach_assistant_guidance(candidate, assistant_guidance)
        return candidates
