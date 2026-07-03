"""Post-simulation check and finalization helpers for ``PipelineBacktestMixin``.

Consolidated from the original ``pipeline_backtest_flow.py`` monolith's
split files (``_checks_mixin`` / ``_finalization_mixin``). Holds the
post-simulation BRAIN-standard alpha checks (``_run_alpha_checks``),
deterministic robustness reports (``_run_robustness_checks``), candidate
finalization (``_finalize_backtest_candidate``), simulation retry logic
(``_simulation_retry_count`` / ``_retry_simulation_candidate``) and the
fusion-candidate factories (``_create_secondary_fusion_candidate`` /
``_try_fusion_top_candidates``).

These mixins are re-assembled at runtime onto ``PipelineBacktestMixin``
(see ``pipeline_backtest_flow.py``).
"""

from __future__ import annotations

import logging

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.scoring.anti_overfit import AntiOverfitService

from brain_alpha_ops.research.pipeline_helpers import blocked_gate as _blocked_gate
from brain_alpha_ops.research.pipeline_helpers import expr_key as _expr_key
from brain_alpha_ops.research.robustness_policy import RobustnessPolicy
from brain_alpha_ops.research.rolling_validation import RollingValidationService

# Preserve the original ``brain_alpha_ops.research.pipeline_backtest_flow``
# logger name so downstream log filters and test caplog assertions keep
# working after the monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.pipeline_backtest_flow")


class _BacktestChecksMixin:
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
        except Exception as exc:
            # P2-18 fix: do not silently swallow check-registry failures.
            # If the registry throws, treat it as a blocking error so the
            # pipeline does not continue as if all checks passed.
            _err_msg = redact_error_message(exc, max_length=200)
            logger.warning("AlphaCheckRegistry failed for %s: %s", redact_text(candidate.alpha_id, max_length=64), _err_msg)
            candidate.submission["alpha_check_report"] = {
                "total": 0, "passed": 0, "failed": 0,
                "passed_overall": False,
                "summary": f"check registry error: {_err_msg}",
                "registry_error": True,
            }
            candidate.gate = _blocked_gate("CHECK_REGISTRY_ERROR", [_err_msg])
            self._event(
                "alpha_checks_error",
                f"AlphaCheckRegistry crashed for {candidate.alpha_id}",
                candidate.alpha_id, level="ERROR"
            )

    def _run_robustness_checks(self, candidate: Candidate, cycle: int) -> None:
        """Attach deterministic robustness reports after official metrics arrive."""
        try:
            anti_report = AntiOverfitService().evaluate(candidate)
            rolling_report = RollingValidationService().evaluate(candidate)
            candidate.submission["anti_overfit_report"] = anti_report
            candidate.submission["rolling_validation_report"] = rolling_report
            policy = RobustnessPolicy().apply(candidate, anti_report, rolling_report)
            self._record_robustness_feedback(candidate, cycle=cycle, policy=policy)
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
            candidate.gate = _blocked_gate("ROBUSTNESS_CHECK_ERROR", [message])
            self._event(
                "robustness_checks_error",
                f"Cycle {cycle}: robustness checks failed for {candidate.alpha_id}: {message}",
                candidate.alpha_id,
                level="WARN",
            )


class _BacktestFinalizationMixin:
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

        # P0-5 fix: preserve original state before clearing so that if the
        # retry also fails the pipeline still has the first attempt's data
        # for diagnostics and scoring fallback.
        if candidate.official_alpha_id:
            candidate.submission["previous_official_alpha_id"] = candidate.official_alpha_id
        if candidate.simulation_id:
            candidate.submission["previous_simulation_id"] = candidate.simulation_id
        candidate.simulation_id = ""
        candidate.official_alpha_id = ""
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
