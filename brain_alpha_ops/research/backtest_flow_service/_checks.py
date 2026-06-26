"""Alpha-check and robustness-check mixin for ``BacktestFlowService``.

Extracted from the original ``backtest_flow_service.py`` monolith. Carries
the post-simulation alpha-check evaluation and the anti-overfit / rolling
validation robustness checks. The module-level ``logger`` lives here
because the alpha-check error path is the only consumer in the original
monolith; the logger name is hardcoded to the original module path so log
records keep their provenance after the split.
"""

from __future__ import annotations

import logging

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.pipeline_helpers import (
    blocked_gate as _blocked_gate,
)
from brain_alpha_ops.research.robustness_policy import RobustnessPolicy
from brain_alpha_ops.research.rolling_validation import RollingValidationService
from brain_alpha_ops.scoring.anti_overfit import AntiOverfitService

logger = logging.getLogger("brain_alpha_ops.research.backtest_flow_service")


class _ChecksMixin:
    """Alpha-check and robustness-check helpers.

    The mixin is consumed by ``BacktestFlowService`` in ``_service``. It
    assumes the host class exposes ``self._pipeline`` (an
    ``AlphaResearchPipeline`` instance).
    """

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
                p.services.runtime._event("alpha_checks_failed",
                    f"Cycle {cycle}: AlphaCheckRegistry found {report.failed_count}/{report.total} failures "
                    f"for {candidate.alpha_id}: {failed_names[:5]}",
                    candidate.alpha_id, level="WARN")
            else:
                p.services.runtime._event("alpha_checks_passed",
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
            p.services.runtime._event(
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
            p.services.runtime._record_robustness_feedback(candidate, cycle=cycle, policy=policy)
            if policy.get("action") != "allow":
                p.services.runtime._event(
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
                p.services.runtime._event(
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
            p.services.runtime._event(
                "robustness_checks_error",
                f"Cycle {cycle}: robustness checks failed for {candidate.alpha_id}: {message}",
                candidate.alpha_id,
                level="WARN",
            )
