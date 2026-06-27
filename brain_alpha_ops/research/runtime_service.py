"""Persistence, observability, and runtime helpers for AlphaResearchPipeline.

Migrated from PipelineRuntimeMixin to standalone class
using composition instead of inheritance.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.models import Candidate, PipelineEvent
from brain_alpha_ops.observability import context_payload, error_payload
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.web_candidates.audit import append_scientific_audit_event

from .pipeline_observability import (
    apply_observability_generation_guidance,
    refresh_observability_throttle,
)
from ._runtime_service_helpers import (
    archive_candidates,
    pipeline_should_stop,
    pipeline_sleep_with_stop,
)
from .strategy_plugins import StrategyPluginRegistry

if TYPE_CHECKING:
    from .pipeline import AlphaResearchPipeline


class RuntimeService:
    """Standalone runtime service using composition.

    Takes a pipeline instance and accesses its state through the reference.
    """

    def __init__(self, pipeline: AlphaResearchPipeline) -> None:
        self._pipeline = pipeline

    def _record_lifecycle(self, candidate: Candidate, stage: str, note: str = ""):
        p = self._pipeline
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
        for existing in reversed(p.lifecycle_records[-50:]):
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
        p.lifecycle_records.append(row)
        if p.run_id:
            p.repository.save_lifecycle_record(p.run_id, row)

    def _record_backtest(self, candidate: Candidate, action: str, *, slot: int = 0, status: str = "", note: str = "", error_context: dict | None = None) -> None:
        p = self._pipeline
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
        p.backtest_records.append(row)
        p.backtest_records = p.backtest_records[-200:]
        if p.run_id:
            p.repository.save_backtest_record(p.run_id, row)

    def _record_robustness_feedback(self, candidate: Candidate, *, cycle: int, policy: dict) -> None:
        self._record_lifecycle(candidate, "robustness_feedback", f"cycle={cycle}; action={policy.get('action', '')}")
        self._record_backtest(candidate, "robustness_feedback", status=str(policy.get("action") or "recorded").upper(), note=f"cycle={cycle}")

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
        p = self._pipeline
        if p.run_id:
            p.repository.save_strategy_lifecycle_record(p.run_id, row)

    def _load_strategy_plugins(self) -> StrategyPluginRegistry:
        p = self._pipeline
        if not getattr(p.config.budget, "strategy_plugins_enabled", False):
            return StrategyPluginRegistry()
        registry = StrategyPluginRegistry.from_specs(list(p.config.budget.strategy_plugin_specs or []))
        if registry.plugins:
            self._event(
                "strategy_plugins_loaded",
                f"Loaded strategy plugins: {', '.join(registry.names())}",
                data={"strategy_plugins": registry.summary()},
                level="INFO",
            )
        if registry.load_errors:
            self._event(
                "strategy_plugins_load_error",
                f"Strategy plugin load errors: {len(registry.load_errors)}",
                data={"strategy_plugins": registry.summary()},
                level="WARN",
            )
        return registry

    def _strategy_plugin_summary(self) -> dict:
        p = self._pipeline
        summary = p.strategy_plugins.summary()
        summary.update({
            "enabled": bool(getattr(p.config.budget, "strategy_plugins_enabled", False)),
            "configured_specs": list(getattr(p.config.budget, "strategy_plugin_specs", []) or []),
        })
        return summary

    def _notify_strategy_plugins(self, action: str, profile: dict, *, cycle: int, reason: str = "", **context: object) -> list[dict]:
        p = self._pipeline
        if not p.strategy_plugins.plugins:
            return []
        payload = {
            "cycle": int(cycle or 0),
            "reason": str(reason or ""),
            "active_profile": p.services.strategy._current_strategy_profile(),
            "active_profile_index": p.strategy_profile_index,
            "strategy_switch_count": p.strategy_switch_count,
            "official_results_since_strategy_switch": p.official_results_since_strategy_switch,
            "ready_since_strategy_switch": p.ready_since_strategy_switch,
            "official_rejections_since_strategy_switch": p.official_rejections_since_strategy_switch,
            "settings": p.config.settings.to_platform_dict()["settings"],
            **context,
        }
        rows = p.strategy_plugins.notify(action, profile=dict(profile or {}), context=payload)
        for row in rows:
            if row.get("status") == "error":
                self._event(
                    "strategy_plugin_error",
                    f"{row.get('plugin')} {action} failed: {row.get('error')}",
                    data={"strategy_plugin": row},
                    level="WARN",
                )
        return rows

    def _recover_persisted_backtest_slots(self) -> None:
        p = self._pipeline
        if not getattr(p.config.budget, "resume_persisted_backtests", True):
            return
        try:
            rows = p.repository.latest_backtest_records(limit=1000)
            recovered = p.backtest_slot_manager.recover_from_records(rows, max_slots=p._visible_backtest_slot_limit())
        except Exception as exc:
            message = redact_error_message(exc, max_length=160)
            self._event("backtest_recovery_failed", message, level="WARN")
            return
        p.recovered_backtest_slot_count = p.backtest_slot_manager.recovered_slot_count
        if p.recovered_backtest_slot_count:
            recovered_rows = [
                {
                    "slot": slot,
                    "alpha_id": candidate.alpha_id,
                    "simulation_id": candidate.simulation_id,
                    "status": candidate.submission.get("simulation_status") or candidate.lifecycle_status,
                    "correlation_id": candidate.submission.get("recovered_correlation_id", ""),
                }
                for slot, candidate in sorted(recovered)
            ]
            self._event(
                "backtest_slots_recovered",
                f"Recovered {p.recovered_backtest_slot_count} persisted backtest slot(s) for polling.",
                data={"backtests": recovered_rows},
            )

    def _official_error_context(self, exc: BrainAPIError, error_code: str, *, phase: str, candidate: Candidate) -> dict:
        return error_payload(exc, error_code=error_code, max_length=240, phase=phase, alpha_id=candidate.alpha_id, simulation_id=candidate.simulation_id, official_alpha_id=candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", ""))

    def _defer_official_cycle(self, cycle: int, pool: list[Candidate], accepted_candidates: list[Candidate], archive_stats: dict[str, int]) -> bool:
        p = self._pipeline
        self._progress(
            "official_deferred", 0, 1,
            f"官方调用已暂停：{p.official_halt_reason}",
            data=p._runtime_data(cycle, pool, accepted_candidates, archive_stats, {
                "retry_seconds": p.config.budget.official_retry_pause_seconds,
                "retry_remaining_seconds": self._official_retry_remaining_seconds(),
            }),
        )
        remaining = self._official_retry_remaining_seconds()
        pause = min(max(0.1, float(p.config.budget.cycle_pause_seconds or 0.1)), p.services.backtest_flow._poll_interval_seconds())
        if remaining:
            pause = min(pause, max(0.1, remaining))
        if not self._sleep_with_stop(pause):
            return False
        return not self._should_stop()

    def _refresh_observability_throttle(self, cycle: int) -> dict:
        from .pipeline import build_research_observability_snapshot
        p = self._pipeline
        result = refresh_observability_throttle(
            storage_dir=p.config.storage_dir, cycle=cycle, generator=p.generator,
            event=self._event, guard_snapshot=p.services.official_validation._observability_official_call_guard_snapshot,
            observability_builder=build_research_observability_snapshot,
        )
        p.observability_generation_guidance = result.generation_guidance
        p.observability_throttle = result.throttle
        blocking_flags = result.blocking_flags
        if blocking_flags:
            reason = "observability blocking flags: " + ", ".join(blocking_flags[:5])
            self._halt_official_calls(reason, p.config.budget.official_retry_pause_seconds, cycle=cycle)
            self._event("official_calls_halted_by_observability", reason, data={"cycle": cycle, "observability": dict(p.observability_throttle)}, level="WARN")
        return p.observability_throttle

    def _apply_observability_generation_guidance(self, snapshot: dict, context: dict, cycle: int) -> None:
        p = self._pipeline
        p.observability_generation_guidance = apply_observability_generation_guidance(snapshot=snapshot, context=context, cycle=cycle, generator=p.generator, event=self._event)

    def _halt_official_calls(self, reason: str, retry_seconds: float | None = None, *, cycle: int = 0):
        p = self._pipeline
        p.official_calls_halted = True
        p.official_halt_reason = reason
        p.official_halt_cycle = int(cycle or 0)
        wait = p.config.budget.official_retry_pause_seconds if retry_seconds is None else retry_seconds
        p.official_resume_at = time.monotonic() + max(0.0, float(wait or 0.0))

    def _maybe_resume_official_calls(self):
        p = self._pipeline
        if p.official_calls_halted and time.monotonic() >= p.official_resume_at:
            p.official_calls_halted = False
            p.official_halt_reason = ""
            p.official_resume_at = 0.0

    def _official_retry_remaining_seconds(self) -> float:
        p = self._pipeline
        if not p.official_calls_halted:
            return 0.0
        return round(max(0.0, p.official_resume_at - time.monotonic()), 1)

    def _archive(self, archive_stats: dict[str, int], archive_samples: list[Candidate], candidates: list[Candidate]):
        archive_candidates(archive_stats, archive_samples, candidates)

    def _should_stop(self) -> bool:
        return pipeline_should_stop(self._pipeline)

    def _sleep_with_stop(self, seconds: float) -> bool:
        return pipeline_sleep_with_stop(self._pipeline, seconds)

    def _event(self, event: str, message: str, alpha_id: str = "", data: dict | None = None, level: str = "INFO"):
        p = self._pipeline
        event_data = {**context_payload(run_id=p.run_id, alpha_id=alpha_id, event=event), **dict(data or {})}
        p.events.append(PipelineEvent(event=event, message=message, alpha_id=alpha_id, level=level, data=event_data))

    def _progress(self, phase: str, current: int, total: int, message: str, alpha_id: str = "", data: dict | None = None):
        p = self._pipeline
        current_data = dict(data or {})
        indeterminate = bool(current_data.pop("progress_indeterminate", False))
        payload_data = {**p.last_runtime_data, **current_data}
        if indeterminate:
            total = 0
            current = max(0, int(current or 0))
            percent = None
        else:
            total = max(1, int(total or 1))
            current = max(0, min(int(current or 0), total))
            percent = round(current / total * 100, 1)
            if p.config.budget.run_forever and phase not in {"completed", "stopped", "failed"}:
                percent = min(percent, 99.0)
        if payload_data:
            p.last_runtime_data = dict(payload_data)
        if "backtests" in payload_data:
            p.last_backtests = list(payload_data.get("backtests") or [])
        elif p.last_backtests:
            payload_data["backtests"] = p.last_backtests
        payload = {
            "phase": phase, "current": current, "total": total, "percent": percent,
            "message": message, "alpha_id": alpha_id, "run_id": p.run_id,
            "continuous": p.config.budget.run_forever, "indeterminate": indeterminate, "data": payload_data,
        }
        if p.progress_callback:
            p.progress_callback(payload)
