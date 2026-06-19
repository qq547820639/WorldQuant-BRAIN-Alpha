"""Official validation and observability guard helpers for AlphaResearchPipeline.

Migrated from PipelineOfficialValidationMixin to standalone class
using composition instead of inheritance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from brain_alpha_ops.models import Candidate

from .official_validation import OfficialValidationService
from .pipeline_helpers import expr_key as _expr_key
from .pipeline_helpers import rank_candidates

if TYPE_CHECKING:
    from .pipeline import AlphaResearchPipeline


class OfficialValidationService_:
    """Standalone official validation service using composition.

    Takes a pipeline instance and accesses its state through the reference.
    """

    def __init__(self, pipeline: AlphaResearchPipeline) -> None:
        self._pipeline = pipeline

    def _validate_for_open_backtest_slots(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        blocked_expressions: set[str],
    ) -> list[Candidate]:
        p = self._pipeline
        pool = rank_candidates(list(pool_by_expression.values()))
        validation_targets = p.services.candidate_pool._validation_targets(pool)
        max_attempts = max(0, int(p.config.budget.max_official_validations_per_cycle))
        if max_attempts <= 0 or not validation_targets:
            return pool

        attempted = 0
        active_limit = p._active_backtest_limit()
        for candidate in validation_targets:
            pool
            active_count = p.backtest_slot_manager.active_count()
            p.services.candidate_pool._preflight_pending_backtest_candidates(pool)
            p.services.runtime._archive(
                archive_stats,
                [],
                self._archive_validation_failures(pool_by_expression, pool, blocked_expressions),
            )
            pool
            pending_count = len(p.services.candidate_pool._pending_backtest_candidates(pool))
            if active_count + pending_count >= active_limit:
                break
            if attempted >= max_attempts or p.official_calls_halted:
                break
            if self._block_observability_duplicate_before_official(candidate, phase="official_validation"):
                p.services.runtime._archive(
                    archive_stats,
                    [],
                    self._archive_validation_failures(pool_by_expression, [candidate], blocked_expressions),
                )
                continue

            self._validate([candidate])
            attempted += 1
            p.services.runtime._archive(
                archive_stats,
                [],
                self._archive_validation_failures(pool_by_expression, [candidate], blocked_expressions),
            )
            if p.official_calls_halted:
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
        p = self._pipeline
        outcome = OfficialValidationService(
            api=p.api,
            settings_payload=p.config.settings.to_platform_dict()["settings"],
            progress=p.services.runtime._progress,
            event=p.services.runtime._event,
            record_lifecycle=p.services.runtime._record_lifecycle,
            halt_official_calls=p.services.runtime._halt_official_calls,
        ).validate(candidates)
        p.official_validation_attempted_count += outcome.attempted
        p.official_validation_passed_count += outcome.passed
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
            elif candidate.lifecycle_status == "high_cloud_similarity_rejected":
                key = _expr_key(candidate)
                pool_by_expression.pop(key, None)
                blocked_expressions.add(key)
                archived.append(candidate)
        return archived

    def _is_observability_duplicate_before_official(self, candidate: Candidate) -> bool:
        p = self._pipeline
        guidance = p.observability_generation_guidance if isinstance(p.observability_generation_guidance, dict) else {}
        return p.official_call_guard.should_block(candidate, guidance)

    def _observability_official_call_guard_snapshot(self) -> dict:
        return self._pipeline.official_call_guard.snapshot()

    def _record_observability_official_call_guard(self, candidate: Candidate, *, phase: str, expression_canonical: str) -> dict:
        p = self._pipeline
        guard = p.official_call_guard.record_block(
            candidate,
            phase=phase,
            expression_canonical=expression_canonical,
        )
        if isinstance(p.observability_throttle, dict):
            p.observability_throttle["official_call_guard"] = guard
        return guard

    def _block_observability_duplicate_before_official(self, candidate: Candidate, *, phase: str) -> bool:
        p = self._pipeline
        guidance = p.observability_generation_guidance if isinstance(p.observability_generation_guidance, dict) else {}
        block = p.official_call_guard.block(candidate, phase=phase, guidance=guidance)
        if not block:
            return False
        if isinstance(p.observability_throttle, dict):
            p.observability_throttle["official_call_guard"] = block["guard"]
        if not block.get("already_recorded"):
            p.services.runtime._record_lifecycle(candidate, "observability_duplicate_blocked", phase)
            p.services.runtime._event(
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
