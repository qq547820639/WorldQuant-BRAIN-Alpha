"""``PipelineRuntimeMixin`` assembly with records and runtime helpers.

Consolidated from the original ``pipeline_runtime.py`` monolith. The
``PipelineRecordsMixin`` (lifecycle/backtest recording and scientific-audit
feedback) and ``PipelineRuntimeHelpersMixin`` (archive/stop/sleep/event/
progress helpers) live here, alongside the final ``PipelineRuntimeMixin``
class that assembles all mixins.
"""

from __future__ import annotations

import time

from brain_alpha_ops.models import Candidate, PipelineEvent
from brain_alpha_ops.observability import context_payload
from brain_alpha_ops.web_candidates.audit import append_scientific_audit_event

from .runtime_mixins import (
    PipelineBacktestRecoveryMixin,
    PipelineObservabilityMixin,
    PipelineOfficialCallsMixin,
    PipelineStrategyPluginsMixin,
)


class PipelineRecordsMixin:
    def _record_lifecycle(self, candidate: Candidate, stage: str, note: str = ""):
        row = {
            "timestamp": time.time(),
            "alpha_id": candidate.alpha_id,
            "official_alpha_id": candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", ""),
            "stage": stage,
            "status": candidate.lifecycle_status,
            "family": candidate.family,
            "hypothesis": candidate.hypothesis,
            "score": candidate.scorecard.get("total_score", 0.0),
            "scorecard": candidate.scorecard,
            "local_quality": candidate.local_quality,
            "validation": candidate.validation,
            "official_metrics": candidate.official_metrics,
            "gate": candidate.gate,
            "simulation_id": candidate.simulation_id,
            "expression": candidate.expression,
            "note": note,
        }
        audit_feedback = self._scientific_audit_feedback(candidate, stage=stage)
        if audit_feedback:
            row["scientific_audit"] = audit_feedback
        event_key = (
            row.get("alpha_id", ""),
            row.get("official_alpha_id", ""),
            row.get("stage", ""),
            row.get("status", ""),
            row.get("simulation_id", ""),
            row.get("note", ""),
        )
        for existing in reversed(self.lifecycle_records[-50:]):
            existing_key = (
                existing.get("alpha_id", ""),
                existing.get("official_alpha_id", ""),
                existing.get("stage", ""),
                existing.get("status", ""),
                existing.get("simulation_id", ""),
                existing.get("note", ""),
            )
            if existing_key == event_key:
                return
        self.lifecycle_records.append(row)
        if self.run_id:
            self.repository.save_lifecycle_record(self.run_id, row)

    def _record_backtest(
        self,
        candidate: Candidate,
        action: str,
        *,
        slot: int = 0,
        status: str = "",
        note: str = "",
        error_context: dict | None = None,
    ) -> None:
        row = {
            "action": action,
            "slot": slot or candidate.submission.get("backtest_slot", 0),
            "alpha_id": candidate.alpha_id,
            "official_alpha_id": candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", ""),
            "simulation_id": candidate.simulation_id,
            "status": status or candidate.submission.get("simulation_status") or candidate.lifecycle_status,
            "lifecycle_status": candidate.lifecycle_status,
            "family": candidate.family,
            "hypothesis": candidate.hypothesis,
            "score": candidate.scorecard.get("total_score", 0.0),
            "poll_count": int(candidate.submission.get("poll_count", 0) or 0),
            "expression": candidate.expression,
            "official_metrics": candidate.official_metrics,
            "gate": candidate.gate,
            "note": note,
        }
        audit_feedback = self._scientific_audit_feedback(candidate, stage=action)
        if audit_feedback:
            row["scientific_audit"] = audit_feedback
        if error_context:
            row["error_context"] = dict(error_context)
            row["retryable"] = bool(error_context.get("retryable"))
            if error_context.get("retry_after") is not None:
                row["retry_after"] = error_context.get("retry_after")
        self.backtest_records.append(row)
        self.backtest_records = self.backtest_records[-200:]
        if self.run_id:
            self.repository.save_backtest_record(self.run_id, row)

    def _record_robustness_feedback(self, candidate: Candidate, *, cycle: int, policy: dict) -> None:
        self._record_lifecycle(candidate, "robustness_feedback", f"cycle={cycle}; action={policy.get('action', '')}")
        self._record_backtest(
            candidate,
            "robustness_feedback",
            status=str(policy.get("action") or "recorded").upper(),
            note=f"cycle={cycle}",
        )

    def _scientific_audit_feedback(self, candidate: Candidate, *, stage: str) -> dict:
        candidate_dict = candidate.to_dict()
        feedback_sources = ["scorecard", "quality_gate"]
        submission = candidate.submission if isinstance(candidate.submission, dict) else {}
        details: dict[str, object] = {"stage": stage}
        if isinstance(submission.get("anti_overfit_report"), dict):
            feedback_sources.append("anti_overfit_report")
            details["anti_overfit_recommendation"] = submission["anti_overfit_report"].get("recommendation")
        if isinstance(submission.get("rolling_validation_report"), dict):
            feedback_sources.append("rolling_validation_report")
            details["rolling_validation_status"] = submission["rolling_validation_report"].get("status")
        if isinstance(submission.get("robustness_policy"), dict):
            feedback_sources.append("robustness_policy")
            details["robustness_action"] = submission["robustness_policy"].get("action")
        extra_fields = candidate.extra_fields if isinstance(candidate.extra_fields, dict) else {}
        has_existing_audit = isinstance(candidate_dict.get("scientific_audit"), dict) or isinstance(extra_fields.get("scientific_audit"), dict)
        has_robustness = any(source in feedback_sources for source in ("anti_overfit_report", "rolling_validation_report", "robustness_policy"))
        if not has_existing_audit and not has_robustness:
            return {}
        audited = append_scientific_audit_event(
            candidate_dict,
            operation="robustness_feedback" if has_robustness else "pipeline_record",
            source="research_pipeline",
            feedback_sources=feedback_sources,
            official_api_called=False,
            details=details,
        )
        return audited.get("scientific_audit", {}) if isinstance(audited.get("scientific_audit"), dict) else {}

    def _record_strategy_lifecycle(self, row: dict) -> None:
        if self.run_id:
            self.repository.save_strategy_lifecycle_record(self.run_id, row)


class PipelineRuntimeHelpersMixin:
    def _archive(
        self,
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        candidates: list[Candidate],
    ):
        for candidate in candidates:
            status = candidate.gate.get("status") or candidate.lifecycle_status or "ARCHIVED"
            if status in {
                "LOCAL_PREFILTER_REJECTED",
                "LOCAL_STANDARD_REJECTED",
                "CANDIDATE_POOL_PRUNED",
                "DUPLICATE_EXPRESSION_SKIPPED",
                "PREVIOUSLY_REJECTED_EXPRESSION_SKIPPED",
            }:
                continue
            archive_stats[status] = archive_stats.get(status, 0) + 1
            if len(archive_samples) < 25 and candidate.official_metrics:
                archive_samples.append(candidate)

    def _should_stop(self) -> bool:
        return bool(self.stop_callback and self.stop_callback())

    def _sleep_with_stop(self, seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(seconds or 0.0))
        while time.monotonic() < deadline:
            if self._should_stop():
                return False
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
        return not self._should_stop()

    def _event(
        self,
        event: str,
        message: str,
        alpha_id: str = "",
        data: dict | None = None,
        level: str = "INFO",
    ):
        event_data = {
            **context_payload(run_id=self.run_id, alpha_id=alpha_id, event=event),
            **dict(data or {}),
        }
        self.events.append(PipelineEvent(event=event, message=message, alpha_id=alpha_id, level=level, data=event_data))

    def _progress(
        self,
        phase: str,
        current: int,
        total: int,
        message: str,
        alpha_id: str = "",
        data: dict | None = None,
    ):
        current_data = dict(data or {})
        indeterminate = bool(current_data.pop("progress_indeterminate", False))
        payload_data = {**self.last_runtime_data, **current_data}
        if indeterminate:
            total = 0
            current = max(0, int(current or 0))
            percent = None
        else:
            total = max(1, int(total or 1))
            current = max(0, min(int(current or 0), total))
            percent = round(current / total * 100, 1)
            if self.config.budget.run_forever and phase not in {"completed", "stopped", "failed"}:
                percent = min(percent, 99.0)
        if payload_data:
            self.last_runtime_data = dict(payload_data)
        if "backtests" in payload_data:
            self.last_backtests = list(payload_data.get("backtests") or [])
        elif self.last_backtests:
            payload_data["backtests"] = self.last_backtests
        payload = {
            "phase": phase,
            "current": current,
            "total": total,
            "percent": percent,
            "message": message,
            "alpha_id": alpha_id,
            "run_id": self.run_id,
            "continuous": self.config.budget.run_forever,
            "indeterminate": indeterminate,
            "data": payload_data,
        }
        if self.progress_callback:
            self.progress_callback(payload)


class PipelineRuntimeMixin(
    PipelineRecordsMixin,
    PipelineStrategyPluginsMixin,
    PipelineBacktestRecoveryMixin,
    PipelineOfficialCallsMixin,
    PipelineObservabilityMixin,
    PipelineRuntimeHelpersMixin,
):
    """Persistence, observability, and runtime helpers for AlphaResearchPipeline."""
