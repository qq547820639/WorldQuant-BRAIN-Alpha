"""Candidate generation phase service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_ast import expression_key, expression_similarity


AssistantGuidanceApplier = Callable[[Candidate, dict[str, Any]], None]


@dataclass
class GenerationPhaseService:
    """Merge generator output with assistant/research-memory/plugin metadata."""

    generator: Any
    max_candidates: int
    dataset_id: str = ""
    attach_assistant_guidance: AssistantGuidanceApplier | None = None
    max_expression_similarity: float = 0.9
    max_generation_attempts: int = 1

    def generate(self, *, assistant_guidance: dict[str, Any] | None = None) -> list[Candidate]:
        candidates: list[Candidate] = []
        seen_expressions: list[str] = []
        max_candidates = max(0, int(self.max_candidates or 0))
        attempts = max(1, int(self.max_generation_attempts or 1))
        threshold = min(1.0, max(0.0, float(self.max_expression_similarity or 0.0)))

        for _attempt in range(attempts):
            remaining = max_candidates - len(candidates)
            if remaining <= 0:
                break
            batch = list(self.generator.generate(remaining, dataset_id=self.dataset_id))
            if not batch:
                break
            added_this_attempt = 0
            for candidate in batch:
                if self._is_duplicate_expression(candidate, seen_expressions, threshold):
                    candidate.lifecycle_status = "duplicate_expression_skipped"
                    continue
                candidates.append(candidate)
                seen_expressions.append(candidate.expression)
                added_this_attempt += 1
                if len(candidates) >= max_candidates:
                    break
            if added_this_attempt == 0:
                break
        if assistant_guidance and self.attach_assistant_guidance:
            for candidate in candidates:
                self.attach_assistant_guidance(candidate, assistant_guidance)
        return candidates

    @staticmethod
    def _is_duplicate_expression(candidate: Candidate, seen_expressions: list[str], threshold: float) -> bool:
        expression = str(candidate.expression or "")
        if not expression:
            return False
        key = expression_key(expression)
        for seen in seen_expressions:
            if key == expression_key(seen):
                return True
            if threshold > 0 and expression_similarity(expression, seen) >= threshold:
                return True
        return False
