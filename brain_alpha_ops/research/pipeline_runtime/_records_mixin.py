"""Lifecycle, backtest, and scientific-audit recording helpers."""

from __future__ import annotations

import time

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.web_candidates.audit import append_scientific_audit_event


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
