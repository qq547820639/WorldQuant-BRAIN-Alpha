"""Persistence, observability, and runtime helpers for AlphaResearchPipeline."""

from __future__ import annotations

import time

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.models import Candidate, PipelineEvent
from brain_alpha_ops.observability import context_payload, error_payload
from brain_alpha_ops.redaction import redact_error_message

from .pipeline_observability import apply_observability_generation_guidance, refresh_observability_throttle
from .strategy_plugins import StrategyPluginRegistry


class PipelineRuntimeMixin:
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
        if error_context:
            row["error_context"] = dict(error_context)
            row["retryable"] = bool(error_context.get("retryable"))
            if error_context.get("retry_after") is not None:
                row["retry_after"] = error_context.get("retry_after")
        self.backtest_records.append(row)
        self.backtest_records = self.backtest_records[-200:]
        if self.run_id:
            self.repository.save_backtest_record(self.run_id, row)

    def _record_strategy_lifecycle(self, row: dict) -> None:
        if self.run_id:
            self.repository.save_strategy_lifecycle_record(self.run_id, row)

    def _load_strategy_plugins(self) -> StrategyPluginRegistry:
        if not getattr(self.config.budget, "strategy_plugins_enabled", False):
            return StrategyPluginRegistry()
        registry = StrategyPluginRegistry.from_specs(list(self.config.budget.strategy_plugin_specs or []))
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
        summary = self.strategy_plugins.summary()
        summary.update(
            {
                "enabled": bool(getattr(self.config.budget, "strategy_plugins_enabled", False)),
                "configured_specs": list(getattr(self.config.budget, "strategy_plugin_specs", []) or []),
            }
        )
        return summary

    def _notify_strategy_plugins(
        self,
        action: str,
        profile: dict,
        *,
        cycle: int,
        reason: str = "",
        **context: object,
    ) -> list[dict]:
        if not self.strategy_plugins.plugins:
            return []
        payload = {
            "cycle": int(cycle or 0),
            "reason": str(reason or ""),
            "active_profile": self._current_strategy_profile(),
            "active_profile_index": self.strategy_profile_index,
            "strategy_switch_count": self.strategy_switch_count,
            "official_results_since_strategy_switch": self.official_results_since_strategy_switch,
            "ready_since_strategy_switch": self.ready_since_strategy_switch,
            "official_rejections_since_strategy_switch": self.official_rejections_since_strategy_switch,
            "settings": self.config.settings.to_platform_dict()["settings"],
            **context,
        }
        rows = self.strategy_plugins.notify(action, profile=dict(profile or {}), context=payload)
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
        if not getattr(self.config.budget, "resume_persisted_backtests", True):
            return
        try:
            rows = self.repository.latest_backtest_records(limit=1000)
            recovered = self.backtest_slot_manager.recover_from_records(
                rows,
                max_slots=self._active_backtest_limit(),
            )
        except Exception as exc:
            message = redact_error_message(exc, max_length=160)
            self._event("backtest_recovery_failed", message, level="WARN")
            return
        self.recovered_backtest_slot_count = self.backtest_slot_manager.recovered_slot_count
        if self.recovered_backtest_slot_count:
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
                f"Recovered {self.recovered_backtest_slot_count} persisted backtest slot(s) for polling.",
                data={"backtests": recovered_rows},
            )

    def _official_error_context(
        self,
        exc: BrainAPIError,
        error_code: str,
        *,
        phase: str,
        candidate: Candidate,
    ) -> dict:
        return error_payload(
            exc,
            error_code=error_code,
            max_length=240,
            phase=phase,
            alpha_id=candidate.alpha_id,
            simulation_id=candidate.simulation_id,
            official_alpha_id=candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", ""),
        )

    def _defer_official_cycle(
        self,
        cycle: int,
        pool: list[Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
    ) -> bool:
        self._progress(
            "official_deferred",
            0,
            1,
            f"官方调用已暂停：{self.official_halt_reason}",
            data=self._runtime_data(
                cycle,
                pool,
                accepted_candidates,
                archive_stats,
                {
                    "retry_seconds": self.config.budget.official_retry_pause_seconds,
                    "retry_remaining_seconds": self._official_retry_remaining_seconds(),
                },
            ),
        )
        remaining = self._official_retry_remaining_seconds()
        pause = min(max(0.1, float(self.config.budget.cycle_pause_seconds or 0.1)), self._poll_interval_seconds())
        if remaining:
            pause = min(pause, max(0.1, remaining))
        if not self._sleep_with_stop(pause):
            return False
        return not self._should_stop()

    def _refresh_observability_throttle(self, cycle: int) -> dict:
        from .pipeline import build_research_observability_snapshot

        result = refresh_observability_throttle(
            storage_dir=self.config.storage_dir,
            cycle=cycle,
            generator=self.generator,
            event=self._event,
            guard_snapshot=self._observability_official_call_guard_snapshot,
            observability_builder=build_research_observability_snapshot,
        )
        self.observability_generation_guidance = result.generation_guidance
        self.observability_throttle = result.throttle
        blocking_flags = result.blocking_flags
        if blocking_flags:
            reason = "observability blocking flags: " + ", ".join(blocking_flags[:5])
            self._halt_official_calls(reason, self.config.budget.official_retry_pause_seconds)
            self._event(
                "official_calls_halted_by_observability",
                reason,
                data={"cycle": cycle, "observability": dict(self.observability_throttle)},
                level="WARN",
            )
        return self.observability_throttle

    def _apply_observability_generation_guidance(self, snapshot: dict, context: dict, cycle: int) -> None:
        self.observability_generation_guidance = apply_observability_generation_guidance(
            snapshot=snapshot,
            context=context,
            cycle=cycle,
            generator=self.generator,
            event=self._event,
        )

    def _halt_official_calls(self, reason: str, retry_seconds: float | None = None):
        self.official_calls_halted = True
        self.official_halt_reason = reason
        wait = self.config.budget.official_retry_pause_seconds if retry_seconds is None else retry_seconds
        self.official_resume_at = time.monotonic() + max(0.0, float(wait or 0.0))

    def _maybe_resume_official_calls(self):
        if self.official_calls_halted and time.monotonic() >= self.official_resume_at:
            self.official_calls_halted = False
            self.official_halt_reason = ""
            self.official_resume_at = 0.0

    def _official_retry_remaining_seconds(self) -> float:
        if not self.official_calls_halted:
            return 0.0
        return round(max(0.0, self.official_resume_at - time.monotonic()), 1)

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
        total = max(1, int(total or 1))
        current = max(0, min(int(current or 0), total))
        percent = round(current / total * 100, 1)
        if self.config.budget.run_forever and phase not in {"completed", "stopped", "failed"}:
            percent = min(percent, 99.0)
        payload_data = {**self.last_runtime_data, **dict(data or {})}
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
            "data": payload_data,
        }
        if self.progress_callback:
            self.progress_callback(payload)
