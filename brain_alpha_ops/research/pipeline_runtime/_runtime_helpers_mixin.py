"""Archive, stop, sleep, event, and progress runtime helpers."""

from __future__ import annotations

import time

from brain_alpha_ops.models import Candidate, PipelineEvent
from brain_alpha_ops.observability import context_payload


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
