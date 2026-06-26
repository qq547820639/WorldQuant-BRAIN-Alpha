"""Observability throttle refresh and generation-guidance helpers."""

from __future__ import annotations

from ..pipeline_observability import (
    apply_observability_generation_guidance,
    refresh_observability_throttle,
)


class PipelineObservabilityMixin:
    def _refresh_observability_throttle(self, cycle: int) -> dict:
        from ..pipeline import build_research_observability_snapshot

        result = refresh_observability_throttle(
            storage_dir=self.config.storage_dir,
            cycle=cycle,
            generator=self.generator,
            event=self._event,
            guard_snapshot=self._observability_official_call_guard_snapshot,
            observability_builder=build_research_observability_snapshot,
        )
        self.observability_generation_guidance = result.generation_guidance
        self.observability_throttle = result.throttle
        blocking_flags = result.blocking_flags
        if blocking_flags:
            reason = "observability blocking flags: " + ", ".join(blocking_flags[:5])
            self._halt_official_calls(reason, self.config.budget.official_retry_pause_seconds)
            self._event(
                "official_calls_halted_by_observability",
                reason,
                data={"cycle": cycle, "observability": dict(self.observability_throttle)},
                level="WARN",
            )
        return self.observability_throttle

    def _apply_observability_generation_guidance(self, snapshot: dict, context: dict, cycle: int) -> None:
        self.observability_generation_guidance = apply_observability_generation_guidance(
            snapshot=snapshot,
            context=context,
            cycle=cycle,
            generator=self.generator,
            event=self._event,
        )
