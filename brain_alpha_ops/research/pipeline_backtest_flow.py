"""Backtest slot, polling, finalization, and fusion helpers for AlphaResearchPipeline."""

from __future__ import annotations

import logging
import time

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from .anti_overfit import AntiOverfitService
from .pipeline_helpers import blocked_gate as _blocked_gate, expr_key as _expr_key, rank_candidates
from .pipeline_state import CycleState
from .robustness_policy import RobustnessPolicy
from .rolling_validation import RollingValidationService

logger = logging.getLogger(__name__)


class PipelineBacktestMixin:
    def _fill_backtest_slots(
        self,
        cycle: int,
        state: CycleState,
    ):
        if self.official_calls_halted:
            return
        active_limit = self._active_backtest_limit()
        open_slots = self.backtest_slot_manager.open_slots(active_limit)
        if not open_slots:
            return

        submission_service = self._backtest_submission_service()
        for slot in open_slots:
            pool = rank_candidates(list(state.pool_by_expression.values()))
            candidate = self._next_backtest_candidate(pool)
            if not candidate:
                return
            if self._block_observability_duplicate_before_official(candidate, phase="official_simulation"):
                state.pool_by_expression.pop(_expr_key(candidate), None)
                state.blocked_expressions.add(_expr_key(candidate))
                self._archive(state.archive_stats, state.archive_samples, [candidate])
                continue
            self._progress(
                "simulation_submit",
                slot - 1,
                active_limit,
                f"回测槽 {slot} 准备提交：{candidate.alpha_id}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
            )
            outcome = submission_service.submit_slot(slot, candidate)
            if not outcome.submitted:
                self._record_backtest(
                    candidate,
                    "submit_failed",
                    slot=slot,
                    note=redact_error_message(outcome.error) if outcome.error else outcome.note,
                    error_context=(
                        self._official_error_context(
                            outcome.error,
                            outcome.error_code or "SIMULATION_SUBMIT_ERROR",
                            phase="simulation_submit",
                            candidate=candidate,
                        )
                        if outcome.error
                        else None
                    ),
                )
                self._progress(
                    "official_deferred" if self.official_calls_halted else "simulation_submit",
                    slot,
                    active_limit,
                    f"回测槽 {slot} 提交延后：{candidate.lifecycle_status}",
                    candidate.alpha_id,
                    data=self._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
                )
                return

            self.backtests_submitted += 1
            self._record_lifecycle(candidate, "simulation_submitted", f"slot={slot}")
            self._record_backtest(candidate, "submitted", slot=slot, status="SUBMITTED")
            self._progress(
                "simulation_submit",
                slot,
                active_limit,
                f"回测槽 {slot} 已提交：{outcome.simulation_id}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, rank_candidates(list(state.pool_by_expression.values())), state.accepted_candidates, state.archive_stats),
            )

    def _next_backtest_candidate(self, pool: list[Candidate]) -> Candidate | None:
        return self.backtest_slot_manager.next_candidate(
            self._backtest_targets(pool),
            key_fn=_expr_key,
        )

    def _handle_slot_submit_error(self, exc: BrainAPIError, candidate: Candidate):
        self._backtest_submission_service()._handle_submit_error(exc, candidate)

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
        if not self.backtest_slots:
            return submitted_this_run
        now = time.monotonic()
        interval = self._poll_interval_seconds()
        polling_service = self._backtest_polling_service()
        for slot, candidate in self.backtest_slot_manager.items_snapshot():
            next_poll_at = float(candidate.submission.get("next_poll_at", 0.0) or 0.0)
            if not force_initial and now < next_poll_at:
                continue
            if force_initial and candidate.submission.get("poll_count", 0):
                continue

            candidate.submission["poll_count"] = int(candidate.submission.get("poll_count", 0) or 0) + 1
            self._progress(
                "simulation_wait",
                slot,
                self._active_backtest_limit(),
                f"轮询回测槽 {slot}：{candidate.alpha_id}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
            outcome = polling_service.poll(candidate, now=now, interval=interval)
            for record in outcome.records:
                self._record_backtest(
                    candidate,
                    record.action,
                    slot=slot,
                    status=record.status,
                    note=record.note,
                    error_context=(
                        self._official_error_context(
                            record.error,
                            record.error_code,
                            phase=record.phase,
                            candidate=candidate,
                        )
                        if record.error
                        else None
                    ),
                )

            self.officially_simulated_count += outcome.official_simulated_increment
            self.official_results_since_strategy_switch += outcome.official_result_increment
            if outcome.official_result:
                self._run_alpha_checks(candidate, outcome.result, cycle)
                self._run_robustness_checks(candidate, cycle)

            if outcome.release_slot:
                self.backtest_slot_manager.release(slot)
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

            self._progress(
                "simulation_wait",
                slot,
                self._active_backtest_limit(),
                f"回测槽 {slot} 状态：{candidate.submission.get('simulation_status') or candidate.lifecycle_status}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
        return submitted_this_run

    def _run_alpha_checks(self, candidate: "Candidate", result: dict, cycle: int) -> None:
        """Run BRAIN-standard alpha checks on a completed simulation result.

        Injects _thresholds into the sim_result for check functions that
        read threshold values.  ERROR-level failures set candidate gate
        to blocked; WARNING/INFO failures are informational only.
        """
        if not self.check_registry:
            return
        try:
            sim_result = dict(result.get("metrics", result))
            # Provide threshold access for check functions
            sim_result["_thresholds"] = self.config.thresholds
            sim_result["settings"] = self.config.settings.to_platform_dict().get("settings", {})
            sim_result["expression"] = candidate.expression
            sim_result["data_fields"] = candidate.data_fields
            sim_result["operators"] = candidate.operators

            report = self.check_registry.evaluate(sim_result)
            candidate.submission["alpha_check_report"] = {
                "total": report.total,
                "passed": report.passed_count,
                "failed": report.failed_count,
                "passed_overall": report.passed,
                "summary": report.summary,
            }
            if not report.passed:
                failed_names = [r.check_name for r in report.results if not r.passed and r.severity == "ERROR"]
                self._event("alpha_checks_failed",
                    f"Cycle {cycle}: AlphaCheckRegistry found {report.failed_count}/{report.total} failures "
                    f"for {candidate.alpha_id}: {failed_names[:5]}",
                    candidate.alpha_id, level="WARN")
            else:
                self._event("alpha_checks_passed",
                    f"Cycle {cycle}: Alpha {candidate.alpha_id} passed {report.passed_count}/{report.total} checks.",
                    candidate.alpha_id, level="INFO")
        except Exception:
            logger.warning("AlphaCheckRegistry failed for %s", candidate.alpha_id, exc_info=True)

    def _run_robustness_checks(self, candidate: Candidate, cycle: int) -> None:
        """Attach deterministic robustness reports after official metrics arrive."""
        try:
            anti_report = AntiOverfitService().evaluate(candidate)
            rolling_report = RollingValidationService().evaluate(candidate)
            candidate.submission["anti_overfit_report"] = anti_report
            candidate.submission["rolling_validation_report"] = rolling_report
            policy = RobustnessPolicy().apply(candidate, anti_report, rolling_report)
            if policy.get("action") != "allow":
                self._event(
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
                self._event(
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
            self._event(
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
        outcome = self._backtest_finalization_service().finalize(
            candidate,
            pool_by_expression=pool_by_expression,
            accepted_candidates=accepted_candidates,
            archive_stats=archive_stats,
            archive_samples=archive_samples,
            blocked_expressions=blocked_expressions,
            submitted_this_run=submitted_this_run,
            auto_submit=auto_submit,
        )
        self.ready_since_strategy_switch += outcome.ready_increment
        self.official_rejections_since_strategy_switch += outcome.rejection_increment
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
        max_retries = max(0, int(self.config.budget.max_simulation_retries or 0))
        retry_count = self._simulation_retry_count(candidate)
        if candidate.official_metrics or retry_count >= max_retries:
            return False

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
        self._record_lifecycle(candidate, "simulation_retry_pending", reason)
        self._event(
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
        outcome = self._secondary_fusion_service().create(
            candidate,
            pool_by_expression=pool_by_expression,
            blocked_expressions=blocked_expressions,
            reason=reason,
        )
        self.produced_count += outcome.produced_increment
        return outcome.candidate

    def _try_fusion_top_candidates(
        self,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        cycle: int,
    ) -> int:
        outcome = self._fusion_candidate_service().create_top_candidate_fusions(
            pool_by_expression,
            blocked_expressions,
            cycle=cycle,
        )
        self.produced_count += outcome.created_count
        return outcome.created_count

    def _poll_interval_seconds(self) -> float:
        api_config = getattr(self.api, "config", None)
        return max(0.1, float(getattr(api_config, "poll_interval_seconds", self.config.official_api.poll_interval_seconds)))
