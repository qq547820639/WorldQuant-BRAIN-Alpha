"""Alpha-check and robustness-check helpers for ``PipelineBacktestMixin``.

Extracted from the original ``pipeline_backtest_flow.py`` monolith. The
post-simulation BRAIN-standard alpha checks (``_run_alpha_checks``) and
the deterministic robustness reports (``_run_robustness_checks``) live
here and are mixed into ``PipelineBacktestMixin`` (see ``_mixin``) to
keep the public class API unchanged while respecting the per-submodule
line budget.
"""

from __future__ import annotations

import logging

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.scoring.anti_overfit import AntiOverfitService

from brain_alpha_ops.research.pipeline_helpers import blocked_gate as _blocked_gate
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
