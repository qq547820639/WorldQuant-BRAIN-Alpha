"""Finalize official backtest candidates after polling completes."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable

from brain_alpha_ops.config import OpsConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from .scoring import build_scorecard, evaluate_quality_gate

logger = logging.getLogger(__name__)


RecordLifecycle = Callable[[Candidate, str, str], None]
RememberAccepted = Callable[[list[Candidate], Candidate], None]
RetrySimulation = Callable[[Candidate, dict[str, Candidate], str], bool]
SecondaryFusion = Callable[[Candidate, dict[str, Candidate], set[str], str], Candidate | None]
ArchiveCandidates = Callable[[dict[str, int], list[Candidate], list[Candidate]], None]
AutoSubmit = Callable[[Candidate, int], int]
ShouldRemove = Callable[[Candidate], bool]
EventCallback = Callable[..., None]
ExpressionKey = Callable[[Candidate], str]


@dataclass
class BacktestFinalizationOutcome:
    submitted_this_run: int
    ready_increment: int = 0
    rejection_increment: int = 0
    retried: bool = False
    secondary_fusion_created: bool = False
    archived: bool = False
    accepted: bool = False
    auto_submitted_increment: int = 0


@dataclass
class BacktestFinalizationService:
    config: OpsConfig
    check_registry: object
    scoring_params: object | None
    record_lifecycle: RecordLifecycle
    remember_accepted: RememberAccepted
    retry_simulation: RetrySimulation
    create_secondary_fusion: SecondaryFusion
    archive: ArchiveCandidates
    try_auto_submit: AutoSubmit
    should_remove_after_official_result: ShouldRemove
    event: EventCallback
    expression_key: ExpressionKey

    def finalize(
        self,
        candidate: Candidate,
        *,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        blocked_expressions: set[str],
        submitted_this_run: int,
        auto_submit: bool,
    ) -> BacktestFinalizationOutcome:
        outcome = BacktestFinalizationOutcome(submitted_this_run=submitted_this_run)
        if candidate.official_metrics:
            self._score_official_candidate(candidate)

        if candidate.gate.get("submission_ready"):
            outcome.ready_increment = 1
            pool_by_expression.pop(self.expression_key(candidate), None)
            self.remember_accepted(accepted_candidates, candidate)
            self.record_lifecycle(candidate, "submission_ready", "通过本地与官方检查")
            outcome.accepted = True
            if auto_submit and candidate.official_metrics:
                increment = self.try_auto_submit(candidate, submitted_this_run)
                outcome.auto_submitted_increment = increment
                outcome.submitted_this_run += increment
            return outcome

        if self.should_remove_after_official_result(candidate):
            if not candidate.official_metrics and self.retry_simulation(
                candidate,
                pool_by_expression,
                "official simulation ended without usable metrics",
            ):
                outcome.retried = True
                return outcome

            child = self.create_secondary_fusion(
                candidate,
                pool_by_expression,
                blocked_expressions,
                "official backtest result needs another research iteration",
            )
            outcome.secondary_fusion_created = child is not None
            outcome.rejection_increment = 1
            pool_by_expression.pop(self.expression_key(candidate), None)
            blocked_expressions.add(self.expression_key(candidate))
            self.archive(archive_stats, archive_samples, [candidate])
            outcome.archived = True
            self.record_lifecycle(candidate, "backtest_failed", "; ".join(candidate.gate.get("failed_reasons", [])))
        elif auto_submit and candidate.official_metrics:
            increment = self.try_auto_submit(candidate, submitted_this_run)
            outcome.auto_submitted_increment = increment
            outcome.submitted_this_run += increment
        return outcome

    def _score_official_candidate(self, candidate: Candidate) -> None:
        settings = candidate.submission.get("settings") if isinstance(candidate.submission, dict) else None
        if not isinstance(settings, dict) or not settings:
            settings = self.config.settings.to_platform_dict()["settings"]
        build_scorecard(
            candidate,
            self.config.thresholds,
            self.config.scoring,
            params=self.scoring_params,
            settings=settings,
        )
        evaluate_quality_gate(candidate, self.config.thresholds, settings=settings)
        check_summary = self._run_submission_checks(candidate)
        gate = candidate.gate or {}
        gate["check_summary"] = check_summary
        candidate.gate = gate
        self._record_experience(candidate)

    def _run_submission_checks(self, candidate: Candidate) -> dict:
        check_summary: dict = {"passed": True, "errors": [], "warnings": [], "info": []}
        try:
            sim_for_check: dict = {"_thresholds": self.config.thresholds, **candidate.official_metrics}
            if candidate.expression:
                sim_for_check["settings"] = self.config.settings.__dict__
                sim_for_check["expression"] = candidate.expression
                sim_for_check["data_fields"] = getattr(candidate, "data_fields", [])
                sim_for_check["operators"] = getattr(candidate, "operators", [])
            check_report = self.check_registry.evaluate(sim_for_check)
            candidate.official_checks = check_report
            check_summary["passed"] = check_report.passed
            for result in check_report.results:
                if result.passed:
                    continue
                entry = {"name": result.check_name, "message": result.message}
                if result.severity == "ERROR":
                    check_summary["errors"].append(entry)
                elif result.severity == "WARNING":
                    check_summary["warnings"].append(entry)
                else:
                    check_summary["info"].append(entry)
            if check_summary["errors"]:
                gate = candidate.gate or {}
                gate.setdefault("failed_reasons", []).extend(
                    f"BRAIN_CHECK:{item['name']}:{item['message']}" for item in check_summary["errors"]
                )
                gate["submission_ready"] = False
                gate["status"] = "BRAIN_CHECK_FAILED"
                candidate.gate = gate
        except Exception as exc:
            check_summary["passed"] = False
            message = redact_error_message(exc)
            check_summary["errors"].append({"name": "check_registry_error", "message": message})
            self.event(
                "alpha_check_error",
                f"AlphaCheckRegistry evaluation failed for {candidate.alpha_id}: {message}",
                level="WARN",
            )
        return check_summary

    def _record_experience(self, candidate: Candidate) -> None:
        try:
            from .experience import record_alpha_result

            record_alpha_result(candidate, self.config.storage_dir)
        except Exception:
            logger.warning("ExperienceDB record failed for %s", candidate.alpha_id, exc_info=True)
