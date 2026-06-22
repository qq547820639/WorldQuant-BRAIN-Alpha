"""Pipeline stall detection monitor — auto-detect and interrupt hung jobs.

Integrated with the web server's job tracking, this monitor periodically
polls active jobs and triggers automatic interruption when a job shows no
progress beyond a configurable timeout. Designed for the goal constraint:
"一旦检测到流程卡顿、挂起或出现状态不明确的情况，必须立即自动中断"
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

# Default stall timeout — how long a job can show no progress before
# it's considered stuck and auto-interrupted.
DEFAULT_STALL_TIMEOUT_SECONDS = 120  # 2 minutes

# Default poll interval — how often the monitor checks job status.
DEFAULT_POLL_INTERVAL_SECONDS = 15

# Terminal states — jobs in these states are ignored by the monitor.
TERMINAL_STATUSES = frozenset({
    "completed", "completed_with_warnings", "failed",
    "stopped", "cancelled", "canceled",
})

@dataclass
class JobStallSnapshot:
    """Snapshot of a job's progress at a point in time."""
    job_id: str
    status: str
    percent_complete: float
    phase: str
    status_message: str
    observed_at: float

@dataclass
class StallMonitorConfig:
    """Configuration for the stall detection monitor."""
    stall_timeout_seconds: float = DEFAULT_STALL_TIMEOUT_SECONDS
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    auto_interrupt: bool = True
    max_retry_count: int = 3  # Max auto-interrupt retries before escalation

class StallMonitor:
    """Monitors pipeline jobs for stalls and triggers auto-interruption.

    Usage:
        monitor = StallMonitor(job_store_getter=lambda: get_jobs())
        monitor.start()
        # ... pipeline runs ...
        monitor.stop()
    """

    def __init__(
        self,
        job_store_getter: Callable[[], Any],
        *,
        config: StallMonitorConfig | None = None,
        on_stall: Callable[[str, JobStallSnapshot], None] | None = None,
        on_interrupt: Callable[[str], None] | None = None,
    ):
        self._get_jobs = job_store_getter
        self.config = config or StallMonitorConfig()
        self._on_stall = on_stall
        self._on_interrupt = on_interrupt
        self._snapshots: dict[str, JobStallSnapshot] = {}
        self._stall_counts: dict[str, int] = {}
        self._interrupt_counts: dict[str, int] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the stall monitor in a background daemon thread."""
        if self._running:
            return
        self._running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="stall-monitor")
        self._thread.start()
        logger.info("StallMonitor started (timeout=%ss, interval=%ss, auto_interrupt=%s)",
                   self.config.stall_timeout_seconds, self.config.poll_interval_seconds,
                   self.config.auto_interrupt)

    def stop(self) -> None:
        """Stop the stall monitor."""
        self._running = False
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("StallMonitor stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop — runs in background thread."""
        while not self._stop.is_set():
            try:
                self._check_all_jobs()
            except Exception:
                logger.exception("StallMonitor check cycle failed")
            self._stop.wait(self.config.poll_interval_seconds)

    def _check_all_jobs(self) -> None:
        """Check all tracked jobs for stalls."""
        try:
            jobs = self._get_jobs()
        except Exception:
            logger.debug("StallMonitor: cannot access job store", exc_info=True)
            return

        now = time.time()
        with self._lock:
            active_ids = set()
            for job_id, job in _iter_job_rows(jobs):
                status = str(job.get("status", "")).lower()
                if status in TERMINAL_STATUSES:
                    self._snapshots.pop(job_id, None)
                    self._stall_counts.pop(job_id, None)
                    continue

                active_ids.add(job_id)
                progress = job.get("progress") or {}
                current = JobStallSnapshot(
                    job_id=job_id,
                    status=status,
                    percent_complete=float(progress.get("percent", progress.get("percent_complete", 0))),
                    phase=str(progress.get("phase", "")),
                    status_message=str(progress.get("status_message", "")),
                    observed_at=now,
                )

                previous = self._snapshots.get(job_id)
                if previous is None:
                    self._snapshots[job_id] = current
                    continue

                # Check if job has progressed
                if (current.percent_complete > previous.percent_complete or
                    current.phase != previous.phase or
                    current.status != previous.status):
                    # Job is making progress — reset stall counter
                    self._snapshots[job_id] = current
                    self._stall_counts.pop(job_id, None)
                    continue

                # No progress — check timeout
                elapsed = now - previous.observed_at
                if elapsed >= self.config.stall_timeout_seconds:
                    stall_count = self._stall_counts.get(job_id, 0) + 1
                    self._stall_counts[job_id] = stall_count
                    logger.warning(
                        "StallMonitor: job %s stalled for %.0fs (phase=%s, progress=%.1f%%, count=%d)",
                        job_id[:12], elapsed, current.phase, current.percent_complete, stall_count
                    )
                    if self._on_stall:
                        self._on_stall(job_id, current)
                    if self.config.auto_interrupt:
                        self._auto_interrupt(job_id, stall_count)

            # Clean up snapshots for jobs that are no longer active
            for stale_id in list(self._snapshots.keys()):
                if stale_id not in active_ids:
                    self._snapshots.pop(stale_id, None)
                    self._stall_counts.pop(stale_id, None)

    def _auto_interrupt(self, job_id: str, stall_count: int) -> None:
        """Auto-interrupt a stalled job."""
        if stall_count > self.config.max_retry_count:
            logger.error(
                "StallMonitor: job %s exceeded max retry count (%d), escalating",
                job_id[:12], self.config.max_retry_count
            )
            return

        logger.warning("StallMonitor: auto-interrupting job %s (attempt %d/%d)",
                      job_id[:12], stall_count, self.config.max_retry_count)
        if self._on_interrupt:
            self._on_interrupt(job_id)

def _iter_job_rows(jobs: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(job_id, job_dict)`` from various job store formats.

    Supported input formats:
    - dict: ``{job_id: job_dict}`` or ``{fallback_id: job_dict}``
    - list[dict]: ``[{"job_id": "...", ...}, ...]``
    - list[tuple]: ``[("job_id", {"job_id": "...", ...}), ...]``

    This handles the 3 different job store representations used across the codebase.
    """
    if isinstance(jobs, dict):
        for fallback_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            job_id = str(job.get("job_id") or job.get("task_id") or fallback_id)
            if job_id:
                yield job_id, job
        return

    if not isinstance(jobs, (list, tuple)):
        return

    for item in jobs:
        if isinstance(item, dict):
            job_id = str(item.get("job_id") or item.get("task_id") or item.get("id") or "")
            if job_id:
                yield job_id, item
            continue
        if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[1], dict):
            job_id = str(item[1].get("job_id") or item[1].get("task_id") or item[0])
            if job_id:
                yield job_id, item[1]

def create_stall_monitor_for_web_server(
    stall_timeout: float = DEFAULT_STALL_TIMEOUT_SECONDS,
    auto_interrupt: bool = True,
) -> StallMonitor:
    """Factory: create a StallMonitor wired into the web server's job store.

    This is the standard integration point for the web console.
    """
    from brain_alpha_ops.web_jobs import job_list as _all_jobs

    config = StallMonitorConfig(
        stall_timeout_seconds=stall_timeout,
        auto_interrupt=auto_interrupt,
    )

    def on_stall(job_id: str, snapshot: JobStallSnapshot) -> None:
        logger.warning(
            "STALL DETECTED: job=%s phase=%s progress=%.1f%% msg=%s",
            job_id[:12], snapshot.phase, snapshot.percent_complete,
            snapshot.status_message[:80]
        )

    def on_interrupt(job_id: str) -> None:
        from brain_alpha_ops.web_jobs import job_update
        job_update(job_id, status="stopped", progress={
            "phase": "interrupted_by_monitor",
            "status_message": "Auto-interrupted: job stalled with no progress",
            "percent_complete": 0,
        })
        logger.warning("Auto-interrupted job %s via StallMonitor", job_id[:12])

    return StallMonitor(
        job_store_getter=_all_jobs,
        config=config,
        on_stall=on_stall,
        on_interrupt=on_interrupt,
    )

# Module-level singleton for easy integration
_GLOBAL_MONITOR: StallMonitor | None = None
_MONITOR_LOCK = threading.Lock()

def ensure_global_monitor(
    stall_timeout: float = DEFAULT_STALL_TIMEOUT_SECONDS,
    auto_interrupt: bool = True,
) -> StallMonitor:
    """Get or create the global stall monitor singleton."""
    global _GLOBAL_MONITOR
    with _MONITOR_LOCK:
        if _GLOBAL_MONITOR is None or not _GLOBAL_MONITOR.running:
            _GLOBAL_MONITOR = create_stall_monitor_for_web_server(
                stall_timeout=stall_timeout,
                auto_interrupt=auto_interrupt,
            )
            _GLOBAL_MONITOR.start()
        return _GLOBAL_MONITOR

def stop_global_monitor() -> None:
    """Stop the global stall monitor if running."""
    global _GLOBAL_MONITOR
    with _MONITOR_LOCK:
        if _GLOBAL_MONITOR and _GLOBAL_MONITOR.running:
            _GLOBAL_MONITOR.stop()
            _GLOBAL_MONITOR = None
