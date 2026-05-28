"""Official validation and observability guard helpers for AlphaResearchPipeline."""

from __future__ import annotations

from brain_alpha_ops.models import Candidate

from .official_validation import OfficialValidationService
from .pipeline_helpers import expr_key as _expr_key, rank_candidates


class PipelineOfficialValidationMixin:
    def _validate_for_open_backtest_slots(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        blocked_expressions: set[str],
    ) -> list[Candidate]:
        pool = rank_candidates(list(pool_by_expression.values()))
        validation_targets = self._validation_targets(pool)
        max_attempts = max(0, int(self.config.budget.max_official_validations_per_cycle))
        if max_attempts <= 0 or not validation_targets:
            return pool

        attempted = 0
        active_limit = self._active_backtest_limit()
        for candidate in validation_targets:
            pool = rank_candidates(list(pool_by_expression.values()))
            active_count = self.backtest_slot_manager.active_count()
            pending_count = len(self._pending_backtest_candidates(pool))
            if active_count + pending_count >= active_limit:
                break
            if attempted >= max_attempts or self.official_calls_halted:
                break
            if self._block_observability_duplicate_before_official(candidate, phase="official_validation"):
                self._archive(
                    archive_stats,
                    [],
                    self._archive_validation_failures(pool_by_expression, [candidate], blocked_expressions),
                )
                continue

            self._validate([candidate])
            attempted += 1
            self._archive(
                archive_stats,
                [],
                self._archive_validation_failures(pool_by_expression, [candidate], blocked_expressions),
            )
            if self.official_calls_halted:
                break
        return rank_candidates(list(pool_by_expression.values()))

    def _filter_observability_duplicate_targets(self, candidates: list[Candidate], *, phase: str) -> list[Candidate]:
        filtered = []
        for candidate in candidates:
            if self._block_observability_duplicate_before_official(candidate, phase=phase):
                continue
            filtered.append(candidate)
        return filtered

    def _validate(self, candidates: list[Candidate]) -> list[Candidate]:
        outcome = OfficialValidationService(
            api=self.api,
            settings_payload=self.config.settings.to_platform_dict()["settings"],
            progress=self._progress,
            event=self._event,
            record_lifecycle=self._record_lifecycle,
            halt_official_calls=self._halt_official_calls,
        ).validate(candidates)
        self.official_validation_attempted_count += outcome.attempted
        self.official_validation_passed_count += outcome.passed
        return outcome.valid

    def _archive_validation_failures(
        self,
        pool_by_expression: dict[str, Candidate],
        validation_targets: list[Candidate],
        blocked_expressions: set[str],
    ) -> list[Candidate]:
        archived = []
        for candidate in validation_targets:
            if candidate.lifecycle_status == "official_validation_failed":
                key = _expr_key(candidate)
                pool_by_expression.pop(key, None)
                blocked_expressions.add(key)
                archived.append(candidate)
            elif candidate.lifecycle_status == "observability_duplicate_blocked":
                key = _expr_key(candidate)
                pool_by_expression.pop(key, None)
                blocked_expressions.add(key)
                archived.append(candidate)
        return archived

    def _is_observability_duplicate_before_official(self, candidate: Candidate) -> bool:
        guidance = self.observability_generation_guidance if isinstance(self.observability_generation_guidance, dict) else {}
        return self.official_call_guard.should_block(candidate, guidance)

    def _observability_official_call_guard_snapshot(self) -> dict:
        return self.official_call_guard.snapshot()

    def _record_observability_official_call_guard(self, candidate: Candidate, *, phase: str, expression_canonical: str) -> dict:
        guard = self.official_call_guard.record_block(
            candidate,
            phase=phase,
            expression_canonical=expression_canonical,
        )
        if isinstance(self.observability_throttle, dict):
            self.observability_throttle["official_call_guard"] = guard
        return guard

    def _block_observability_duplicate_before_official(self, candidate: Candidate, *, phase: str) -> bool:
        guidance = self.observability_generation_guidance if isinstance(self.observability_generation_guidance, dict) else {}
        block = self.official_call_guard.block(candidate, phase=phase, guidance=guidance)
        if not block:
            return False
        if isinstance(self.observability_throttle, dict):
            self.observability_throttle["official_call_guard"] = block["guard"]
        self._record_lifecycle(candidate, "observability_duplicate_blocked", phase)
        self._event(
            "observability_duplicate_official_call_blocked",
            block["reason"],
            candidate.alpha_id,
            data={
                "phase": phase,
                "expression_canonical": block["expression_canonical"],
                "observability_generation_guidance": dict(guidance),
                "observability_official_call_guard": block["guard"],
            },
            level="WARN",
        )
        return True
