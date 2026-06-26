"""Shared state and helper methods for the cloud sync job service."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from brain_alpha_ops.brain_api.user_alpha_sync import sync_range_from_payload

from .._helpers import (
    _SCAN_OBSERVABILITY_KEYS,
    _cloud_scan_status_message,
    _scan_observability,
    _timing_payload,
)
from .._types import (
    ErrorPayload,
    JobStoreLike,
    SafeErrorMessage,
    SyncJobCancelled,
)

logger = logging.getLogger("brain_alpha_ops.web_cloud.sync_job._service")


class SyncJobContext:
    """Mutable state and helper methods for a single sync job run.

    Encapsulates the shared mutable state (stats, stop flags, heartbeat
    counters) and the nested closures that the original
    ``run_sync_job_service`` defined inline. Behaviour is preserved by
    keeping every reference pointing at the same underlying dict/list
    instances stored on ``self``.
    """

    _HB_INTERVAL = 120.0  # 2 minutes, well under 5-min watchdog

    def __init__(
        self,
        job_id: str,
        payload: dict[str, Any],
        *,
        store: JobStoreLike,
        safe_error_message: SafeErrorMessage,
        error_payload: ErrorPayload,
    ) -> None:
        self.job_id = job_id
        self.payload = payload
        self.store = store
        self.safe_error_message = safe_error_message
        self.error_payload = error_payload
        self.sync_range = sync_range_from_payload(payload)
        self.context_only = bool(payload.get("contextOnly") or payload.get("context_only"))
        self.started_at = time.time()
        self.stats: dict[str, Any] = {
            "range": self.sync_range,
            "context_only": self.context_only,
            "scanned": 0,
            "total": 0,
            "added": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
        }
        self.context_error = ""
        self.context_warnings: list[str] = []
        self.stop_state = {
            "requested": False,
            "message": "云端同步已停止。",
            "status_message": "云端同步已停止，可调整范围后重试。",
        }
        self.heartbeat_stop = threading.Event()
        self.heartbeat_count = [0]
        self.heartbeat_thread: threading.Thread | None = None
        self.saved: list[dict[str, Any]] = []
        self.fields: list[dict[str, Any]] = []
        self.operators: list[dict[str, Any]] = []
        self.datasets: list[dict[str, Any]] = []

    # ---- watchdog heartbeat daemon ----
    def _heartbeat_loop(self) -> None:
        while not self.heartbeat_stop.wait(self._HB_INTERVAL):
            self.heartbeat_count[0] += 1
            try:
                self.store.update(
                    self.job_id,
                    status="running",
                    progress={
                        "task_id": self.job_id,
                        "job_id": self.job_id,
                        "operation": "sync_alphas",
                        "phase": "heartbeat",
                        "status_code": "HEARTBEAT",
                        "status_message": f"Sync still active ({self.heartbeat_count[0]} heartbeats).",
                        "message": f"Sync still active ({self.heartbeat_count[0]} heartbeats).",
                        "heartbeat": {
                            "count": self.heartbeat_count[0],
                            "source": "watchdog_keepalive",
                            "elapsed": round(time.time() - self.started_at, 1),
                        },
                        **self.stats,
                        **_timing_payload(self.started_at, done=int(self.stats.get("scanned", 0) or 0)),
                    },
                )
            except (OSError, ValueError, TypeError):
                pass

    def start_heartbeat(self) -> None:
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name=f"sync-hb-{self.job_id}"
        )
        self.heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self.heartbeat_stop.set()

    # ---- cancellation ----
    def cancel_requested(self) -> bool:
        checker = getattr(self.store, "is_cancelled", None)
        return bool(callable(checker) and checker(self.job_id))

    def request_stop(self, message: str, status_message: str | None = None) -> None:
        self.stop_state["requested"] = True
        self.stop_state["message"] = message
        self.stop_state["status_message"] = status_message or message

    def ensure_not_cancelled(self) -> None:
        if self.cancel_requested():
            self.request_stop("云端同步已停止。", "云端同步已停止，可调整范围后重试。")
            raise SyncJobCancelled(self.stop_state["message"])
        if self.stop_state["requested"]:
            raise SyncJobCancelled(self.stop_state["message"])

    def on_dataset_fallback(self, message: str, exc: Exception) -> None:
        self.context_warnings.append(f"{message}: {self.safe_error_message(exc)}")

    def mark_cancelled(self) -> None:
        self.store.update(
            self.job_id,
            status="cancelled",  # P0-2 unified (was "stopped"),
            result={
                "ok": False,
                "status": "cancelled",
                "range": self.sync_range,
                **self.stats,
                **_timing_payload(self.started_at, done=int(self.stats.get("scanned", 0) or 0)),
                "message": self.stop_state["message"],
            },
            progress={
                "task_id": self.job_id,
                "job_id": self.job_id,
                "operation": "sync_alphas",
                "phase": "stopped",
                "status_code": "STOPPED",
                "status_message": self.stop_state["status_message"],
                "message": self.stop_state["status_message"],
                "percent": 100,
                "percent_complete": 100,
                **self.stats,
                **_timing_payload(self.started_at, done=int(self.stats.get("scanned", 0) or 0)),
            },
        )

    # ---- progress callbacks ----
    def on_page(self, progress: dict[str, Any]) -> bool:
        self.ensure_not_cancelled()
        if (
            "total" in progress
            and "api_reported_total" not in progress
            and "filter_window_count" not in progress
        ):
            # Legacy scan payloads used "total" for the API filter-window
            # count. Preserve it as a reference only, never as completion.
            progress = {
                **progress,
                "api_reported_total": progress.get("total"),
                "filter_window_count": progress.get("total"),
            }
        elif "api_reported_total" in progress and "filter_window_count" not in progress:
            progress = {**progress, "filter_window_count": progress.get("api_reported_total")}
        elif "filter_window_count" in progress and "api_reported_total" not in progress:
            progress = {**progress, "api_reported_total": progress.get("filter_window_count")}
        self.stats["scanned"] = int(progress.get("scanned", self.stats["scanned"]) or 0)
        self.stats["page_size"] = int(progress.get("page_size", self.stats.get("page_size", 0)) or 0)
        self.stats["offset"] = int(progress.get("offset", self.stats.get("offset", 0)) or 0)
        for key in _SCAN_OBSERVABILITY_KEYS:
            self.stats.pop(key, None)
        self.stats.update(_scan_observability(progress))
        status_message = _cloud_scan_status_message(self.stats)
        scan_stats = dict(self.stats)
        scan_stats.pop("total", None)
        self.store.update(
            self.job_id,
            status="running",
            progress={
                "task_id": self.job_id,
                "job_id": self.job_id,
                "operation": "sync_alphas",
                "phase": "scan",
                "status_code": "SCAN",
                "status_message": status_message,
                "message": status_message,
                **scan_stats,
                **_timing_payload(self.started_at, done=self.stats["scanned"]),
            },
        )
        if self.cancel_requested():
            self.request_stop("云端同步已停止。", "云端同步已停止，可调整范围后重试。")
            return False
        return True

    def on_fields_progress(self, progress: dict[str, Any]) -> bool:
        self.ensure_not_cancelled()
        self.store.update(
            self.job_id,
            status="running",
            progress={
                "task_id": self.job_id,
                "job_id": self.job_id,
                "operation": "sync_alphas",
                "phase": "context",
                "status_code": "CONTEXT_FIELDS",
                "status_message": f"正在刷新官方字段缓存: {progress.get('scanned', 0)} / {progress.get('total') or '未知'}",
                "message": f"正在刷新官方字段缓存: {progress.get('scanned', 0)} / {progress.get('total') or '未知'}",
                "current": 1,
                "total_steps": 3,
                "fields_count": int(progress.get("scanned", 0) or 0),
                "fields_total": int(progress.get("total", 0) or 0),
                **self.stats,
                **_timing_payload(
                    self.started_at,
                    done=int(progress.get("scanned", 0) or 0),
                    total=int(progress.get("total", 0) or 0),
                ),
            },
        )
        if self.cancel_requested():
            self.request_stop("云端同步已停止。", "云端同步已停止，可调整范围后重试。")
            return False
        return True

    def on_operators_progress(self, progress: dict[str, Any]) -> bool:
        self.ensure_not_cancelled()
        self.store.update(
            self.job_id,
            status="running",
            progress={
                "task_id": self.job_id,
                "job_id": self.job_id,
                "operation": "sync_alphas",
                "phase": "context",
                "status_code": "CONTEXT_OPERATORS",
                "status_message": f"正在刷新官方算子缓存: {progress.get('scanned', 0)} / {progress.get('total') or '未知'}",
                "message": f"正在刷新官方算子缓存: {progress.get('scanned', 0)} / {progress.get('total') or '未知'}",
                "current": 2,
                "total_steps": 3,
                "fields_count": len(self.fields),
                "operators_count": int(progress.get("scanned", 0) or 0),
                "operators_total": int(progress.get("total", 0) or 0),
                **self.stats,
                **_timing_payload(
                    self.started_at,
                    done=int(progress.get("scanned", 0) or 0),
                    total=int(progress.get("total", 0) or 0),
                ),
            },
        )
        if self.cancel_requested():
            self.request_stop("云端同步已停止。", "云端同步已停止，可调整范围后重试。")
            return False
        return True
