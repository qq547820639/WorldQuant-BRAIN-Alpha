"""Backtest slot, polling, finalization, and fusion helpers for AlphaResearchPipeline.

Migrated from PipelineBacktestMixin to standalone class
using composition instead of inheritance.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message, redact_text

from .anti_overfit import AntiOverfitService
from .pipeline_helpers import blocked_gate as _blocked_gate
from .pipeline_helpers import expr_key as _expr_key
from .pipeline_helpers import rank_candidates
from .pipeline_state import CycleState
from .robustness_policy import RobustnessPolicy
from .rolling_validation import RollingValidationService

if TYPE_CHECKING:
    from .pipeline import AlphaResearchPipeline

logger = logging.getLogger(__name__)


class BacktestFlowService:
    """Standalone backtest flow service using composition.

    Takes a pipeline instance and accesses its state through the reference.
    """

    def __init__(self, pipeline: AlphaResearchPipeline) -> None:
        self._pipeline = pipeline

    def _fill_backtest_slots(self, cycle: int, state: CycleState):
        p = self._pipeline
        if p.official_calls_halted:
            return
        active_limit = p._active_backtest_limit()
        open_slots = p.backtest_slot_manager.open_slots(active_limit)
        if not open_slots:
            return

        submission_service = p._backtest_submission_service()
        for slot in open_slots:
            pool = rank_candidates(list(state.pool_by_expression.values()))
            candidate = self._next_backtest_candidate(pool)
            if not candidate:
                return
            if p._block_observability_duplicate_before_official(candidate, phase="official_simulation"):
                state.pool_by_expression.pop(_expr_key(candidate), None)
                state.blocked_expressions.add(_expr_key(candidate))
                p._archive(state.archive_stats, state.archive_samples, [candidate])
                continue
            p._progress(
                "simulation_submit",
                slot - 1,
                active_limit,
                f"回测槽 {slot} 准备提交：{candidate.alpha_id}",
                candidate.alpha_id,
                data=p._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
            )
            outcome = submission_service.submit_slot(slot, candidate)
            if not outcome.submitted:
                p._record_backtest(
                    candidate,
                    "submit_failed",
                    slot=slot,
                    note=redact_error_message(outcome.error) if outcome.error else outcome.note,
                    error_context=(
                        p._official_error_context(
                            outcome.error,
                            outcome.error_code or "SIMULATION_SUBMIT_ERROR",
                            phase="simulation_submit",
                            candidate=candidate,
                        )
                        if outcome.error
                        else None
                    ),
                )
                p._progress(
                    "official_deferred" if p.official_calls_halted else "simulation_submit",
                    slot,
                    active_limit,
                    f"回测槽 {slot} 提交延后：{candidate.lifecycle_status}",
                    candidate.alpha_id,
                    data=p._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
                )
                return

            p.backtests_submitted += 1
            p._record_lifecycle(candidate, "simulation_submitted", f"slot={slot}")
            p._record_backtest(candidate, "submitted", slot=slot, status="SUBMITTED")
            p._progress(
                "simulation_submit",
                slot,
                active_limit,
                f"回测槽 {slot} 已提交：{outcome.simulation_id}",
                candidate.alpha_id,
                data=p._runtime_data(cycle, rank_candidates(list(state.pool_by_expression.values())), state.accepted_candidates, state.archive_stats),
            )

    def _next_backtest_candidate(self, pool: list[Candidate]) -> Candidate | None:
        p = self._pipeline
        return p.backtest_slot_manager.next_candidate(
            p._backtest_targets(pool),
            key_fn=_expr_key,
        )

    def _handle_slot_submit_error(self, exc, candidate: Candidate):
        self._pipeline._backtest_submission_service()._handle_submit_error(exc, candidate)

    def _poll_due_backtests(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        blocked_expressions: set[str],
        submitted_this_run: int,
        auto_submit: bool,
        *,
        force_initial: bool = False,
    ) -> int:
        p = self._pipeline
        if not p.backtest_slots:
            return submitted_this_run
        now = time.monotonic()
        interval = self._poll_interval_seconds()
        polling_service = p._backtest_polling_service()
        for slot, candidate in p.backtest_slot_manager.items_snapshot():
            next_poll_at = float(candidate.submission.get("next_poll_at", 0.0) or 0.0)
            if not force_initial:
                if now < next_poll_at:
                    continue

            candidate.submission["poll_count"] = int(candidate.submission.get("poll_count", 0) or 0) + 1
            p._progress(
                "simulation_wait",
                slot,
                p._active_backtest_limit(),
                f"轮询回测槽 {slot}：{candidate.alpha_id}",
                candidate.alpha_id,
                data=p._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
            outcome = polling_service.poll(candidate, now=now, interval=interval)
            for record in outcome.records:
                p._record_backtest(
                    candidate,
                    record.action,
                    slot=slot,
                    status=record.status,
                    note=record.note,
                    error_context=(
                        p._official_error_context(
                            record.error,
                            record.error_code,
                            phase=record.phase,
                            candidate=candidate,
                        )
                        if record.error
                        else None
                    ),
                )

            p.officially_simulated_count += outcome.official_simulated_increment
            p.official_results_since_strategy_switch += outcome.official_result_increment
            if outcome.official_result:
                self._run_alpha_checks(candidate, outcome.result, cycle)
                self._run_robustness_checks(candidate, cycle)

            if outcome.release_slot:
                p.backtest_slot_manager.release(slot)
            if outcome.finalize:
                submitted_this_run = self._finalize_backtest_candidate(
                    candidate,
                    pool_by_expression,
                    accepted_candidates,
                    archive_stats,
                    archive_samples,
                    blocked_expressions,
                    submitted_this_run,
                    auto_submit,
                )
            if outcome.halted:
                return submitted_this_run

            p._progress(
                "simulation_wait",
                slot,
                p._active_backtest_limit(),
                f"回测槽 {slot} 状态：{candidate.submission.get('simulation_status') or candidate.lifecycle_status}",
                candidate.alpha_id,
                data=p._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
        return submitted_this_run

    def _run_alpha_checks(self, candidate: Candidate, result: dict, cycle: int) -> None:
        p = self._pipeline
        if not p.check_registry:
            return
        try:
            sim_result = dict(result.get("metrics", result))
            sim_result["_thresholds"] = p.config.thresholds
            sim_result["settings"] = p.config.settings.to_platform_dict().get("settings", {})
            sim_result["expression"] = candidate.expression
            sim_result["data_fields"] = candidate.data_fields
            sim_result["operators"] = candidate.operators

            report = p.check_registry.evaluate(sim_result)
            candidate.submission["alpha_check_report"] = {
                "total": report.total,
                "passed": report.passed_count,
                "failed": report.failed_count,
                "passed_overall": report.passed,
                "summary": report.summary,
            }
            if not report.passed:
                failed_names = [r.check_name for r in report.results if not r.passed and r.severity == "ERROR"]
                p._event("alpha_checks_failed",
                    f"Cycle {cycle}: AlphaCheckRegistry found {report.failed_count}/{report.total} failures "
                    f"for {candidate.alpha_id}: {failed_names[:5]}",
                    candidate.alpha_id, level="WARN")
            else:
                p._event("alpha_checks_passed",
                    f"Cycle {cycle}: Alpha {candidate.alpha_id} passed {report.passed_count}/{report.total} checks.",
                    candidate.alpha_id, level="INFO")
        except Exception as exc:
            _err_msg = redact_error_message(exc, max_length=200)
            logger.warning("AlphaCheckRegistry failed for %s: %s", redact_text(candidate.alpha_id, max_length=64), _err_msg)
            candidate.submission["alpha_check_report"] = {
                "total": 0, "passed": 0, "failed": 0,
                "passed_overall": False,
                "summary": f"check registry error: {_err_msg}",
                "registry_error": True,
            }
            candidate.gate = _blocked_gate("CHECK_REGISTRY_ERROR", [_err_msg])
            p._event(
                "alpha_checks_error",
                f"AlphaCheckRegistry crashed for {candidate.alpha_id}",
                candidate.alpha_id, level="ERROR"
            )

    def _run_robustness_checks(self, candidate: Candidate, cycle: int) -> None:
        p = self._pipeline
        try:
            anti_report = AntiOverfitService().evaluate(candidate)
            rolling_report = RollingValidationService().evaluate(candidate)
            candidate.submission["anti_overfit_report"] = anti_report
            candidate.submission["rolling_validation_report"] = rolling_report
            policy = RobustnessPolicy().apply(candidate, anti_report, rolling_report)
            p._record_robustness_feedback(candidate, cycle=cycle, policy=policy)
            if policy.get("action") != "allow":
                p._event(
                    "robustness_checks_caution",
                    f"Cycle {cycle}: robustness checks flagged {candidate.alpha_id}.",
                    candidate.alpha_id,
                    level="WARN",
                    data={
                        "anti_overfit": anti_report.get("recommendation"),
                        "rolling_validation": rolling_report.get("status"),
                        "robustness_policy": policy,
                    },
                )
            else:
                p._event(
                    "robustness_checks_passed",
                    f"Cycle {cycle}: robustness checks completed for {candidate.alpha_id}.",
                    candidate.alpha_id,
                    level="INFO",
                    data={
                        "anti_overfit_score": anti_report.get("score"),
                        "rolling_validation_score": rolling_report.get("score"),
                    },
                )
        except Exception as exc:
            message = redact_error_message(exc)
            candidate.submission["robustness_check_error"] = message
            p._event(
                "robustness_checks_error",
                f"Cycle {cycle}: robustness checks failed for {candidate.alpha_id}: {message}",
                candidate.alpha_id,
                level="WARN",
            )

    def _finalize_backtest_candidate(
        self,
        candidate: Candidate,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        blocked_expressions: set[str],
        submitted_this_run: int,
        auto_submit: bool,
    ) -> int:
        p = self._pipeline
        outcome = p._backtest_finalization_service().finalize(
            candidate,
            pool_by_expression=pool_by_expression,
            accepted_candidates=accepted_candidates,
            archive_stats=archive_stats,
            archive_samples=archive_samples,
            blocked_expressions=blocked_expressions,
            submitted_this_run=submitted_this_run,
            auto_submit=auto_submit,
        )
        p.ready_since_strategy_switch += outcome.ready_increment
        p.official_rejections_since_strategy_switch += outcome.rejection_increment
        return outcome.submitted_this_run

    def _simulation_retry_count(self, candidate: Candidate) -> int:
        try:
            return max(0, int(candidate.submission.get("simulation_retry_count", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def _retry_simulation_candidate(
        self,
        candidate: Candidate,
        pool_by_expression: dict[str, Candidate],
        reason: str,
    ) -> bool:
        p = self._pipeline
        max_retries = max(0, int(p.config.budget.max_simulation_retries or 0))
        retry_count = self._simulation_retry_count(candidate)
        if candidate.official_metrics or retry_count >= max_retries:
            return False

        if candidate.official_metrics:
            candidate.submission["previous_official_metrics"] = dict(candidate.official_metrics)
        if candidate.official_alpha_id:
            candidate.submission["previous_official_alpha_id"] = candidate.official_alpha_id
        if candidate.simulation_id:
            candidate.submission["previous_simulation_id"] = candidate.simulation_id
        candidate.simulation_id = ""
        candidate.official_alpha_id = ""
        candidate.official_metrics = {}
        candidate.lifecycle_status = "simulation_retry_pending"
        candidate.submission["simulation_retry_count"] = retry_count + 1
        candidate.submission["simulation_status"] = "RETRY_PENDING"
        candidate.submission["next_poll_at"] = 0.0
        candidate.submission["poll_count"] = 0
        candidate.gate = _blocked_gate("SIMULATION_RETRY_PENDING", [reason])
        pool_by_expression[_expr_key(candidate)] = candidate
        p._record_lifecycle(candidate, "simulation_retry_pending", reason)
        p._event(
            "simulation_retry_scheduled",
            f"Retry {retry_count + 1}/{max_retries} scheduled after official simulation failure.",
            candidate.alpha_id,
            data={"retry_count": retry_count + 1, "max_retries": max_retries},
            level="WARN",
        )
        return True

    def _create_secondary_fusion_candidate(
        self,
        candidate: Candidate,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        reason: str,
    ) -> Candidate | None:
        p = self._pipeline
        outcome = p._secondary_fusion_service().create(
            candidate,
            pool_by_expression=pool_by_expression,
            blocked_expressions=blocked_expressions,
            reason=reason,
        )
        p.produced_count += outcome.produced_increment
        return outcome.candidate

    def _try_fusion_top_candidates(
        self,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        cycle: int,
    ) -> int:
        p = self._pipeline
        outcome = p._fusion_candidate_service().create_top_candidate_fusions(
            pool_by_expression,
            blocked_expressions,
            cycle=cycle,
        )
        p.produced_count += outcome.created_count
        return outcome.created_count

    def _poll_interval_seconds(self) -> float:
        p = self._pipeline
        api_config = getattr(p.api, "config", None)
        return max(0.1, float(getattr(api_config, "poll_interval_seconds", p.config.official_api.poll_interval_seconds)))
