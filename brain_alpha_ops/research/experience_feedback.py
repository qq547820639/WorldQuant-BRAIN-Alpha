"""Experience and research-memory feedback service."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from brain_alpha_ops.research.experience import get_winning_patterns
from brain_alpha_ops.research.memory import ResearchMemory


EXPERIENCE_FEEDBACK_SCHEMA_VERSION = "experience_feedback.v1"

EventCallback = Callable[..., None]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExperienceFeedbackResult:
    applied: bool
    source: str = ""
    sample_size: int = 0
    top_operators: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXPERIENCE_FEEDBACK_SCHEMA_VERSION,
            "applied": self.applied,
            "source": self.source,
            "sample_size": self.sample_size,
            "top_operators": list(self.top_operators),
            "reason": self.reason,
        }


class ExperienceFeedbackService:
    """Apply winning-pattern or memory guidance on scheduled cycles."""

    def __init__(
        self,
        *,
        storage_dir: str,
        generator: Any,
        event: EventCallback | None = None,
        memory_factory: Callable[[str], ResearchMemory] = ResearchMemory,
        winning_patterns: Callable[..., dict[str, Any]] = get_winning_patterns,
        log: logging.Logger = logger,
    ) -> None:
        self.storage_dir = storage_dir
        self.generator = generator
        self.event = event
        self.memory_factory = memory_factory
        self.winning_patterns = winning_patterns
        self.log = log

    def apply(self, cycle: int) -> ExperienceFeedbackResult:
        if cycle <= 0 or cycle % 5 != 0:
            return ExperienceFeedbackResult(applied=False, reason="not_feedback_cycle")
        try:
            patterns = self.winning_patterns(self.storage_dir, min_sharpe=1.5, min_sample=2)
            if int(patterns.get("sample_size", 0) or 0) >= 2:
                self.generator.set_experience_guidance(patterns)
                result = ExperienceFeedbackResult(
                    applied=True,
                    source="winning_patterns",
                    sample_size=int(patterns.get("sample_size", 0) or 0),
                    top_operators=tuple(str(item) for item in (patterns.get("top_operators") or [])[:5]),
                )
                self._emit(cycle, result, "experience_feedback")
                return result

            memory_guidance = self.memory_factory(self.storage_dir).generation_guidance(top_n=10)
            if int(memory_guidance.get("sample_size", 0) or 0) >= 3:
                self.generator.set_experience_guidance(memory_guidance)
                result = ExperienceFeedbackResult(
                    applied=True,
                    source="research_memory",
                    sample_size=int(memory_guidance.get("sample_size", 0) or 0),
                    top_operators=tuple(str(item) for item in (memory_guidance.get("top_operators") or [])[:5]),
                )
                self._emit(cycle, result, "memory_feedback")
                return result
            return ExperienceFeedbackResult(applied=False, reason="insufficient_samples")
        except Exception:
            self.log.warning("Experience feedback unavailable in cycle %s", cycle, exc_info=True)
            return ExperienceFeedbackResult(applied=False, reason="error")

    def _emit(self, cycle: int, result: ExperienceFeedbackResult, event_name: str) -> None:
        if not self.event:
            return
        if result.source == "winning_patterns":
            self.event(
                event_name,
                f"Cycle {cycle}: Guiding generation with {result.sample_size} winning patterns. "
                f"Top operators: {list(result.top_operators)}",
            )
        else:
            self.event(
                event_name,
                f"Cycle {cycle}: Guiding generation with local memory from {result.sample_size} candidates. "
                f"Top operators: {list(result.top_operators)}",
            )
