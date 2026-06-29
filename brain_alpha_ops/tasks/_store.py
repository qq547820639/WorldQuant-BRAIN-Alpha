"""Thread-safe job state store with optional JSON persistence.

The store keeps the runtime payload narrow: status, progress, result,
cancellation flag, and error. It never persists request credentials.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from brain_alpha_ops.core_state import JOB_ACTIVE_STATUSES as ACTIVE_STATUSES
from brain_alpha_ops.core_state import JOB_TERMINAL_STATUSES as TERMINAL_STATUSES

from ._compaction import _job_safe
from ._constants import (
    DEFAULT_MAX_PERSISTENCE_LOAD_BYTES,
    DEFAULT_RECOVERY_ERROR,
    DEFAULT_WATCHDOG_TIMEOUT_SECONDS,
)
from ._watchdog import (
    _mark_watchdog_failed,
    _reject_watchdog_terminal_update,
    _updated_at,
    _watchdog_should_stop,
)


class JobStore:
    """Thread-safe job state store with optional JSON persistence."""

    def __init__(
        self,
        persistence_path: str | Path | None = None,
        *,
        job_prefix: str = "job",
        max_jobs: int = 200,
        recover_active_as: str = "failed",
        max_load_bytes: int = DEFAULT_MAX_PERSISTENCE_LOAD_BYTES,
        watchdog_timeout_seconds: float = DEFAULT_WATCHDOG_TIMEOUT_SECONDS,
    ):
        self.lock = threading.Lock()
        self.jobs: dict[str, dict[str, Any]] = {}
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self.job_prefix = job_prefix or "job"
        self.max_jobs = max(1, int(max_jobs or 1))
        self.recover_active_as = recover_active_as
        self.max_load_bytes = max(1, int(max_load_bytes or 1))
        self.watchdog_timeout_seconds = max(0.0, float(watchdog_timeout_seconds or 0.0))
        self.last_persist_error = ""
        self.persistence_load_skipped = False
        self._load()

    def create(self, initial: dict[str, Any] | None = None) -> str:
        with self.lock:
            return self._create_locked(initial)

    def create_if_no_active(
        self,
        initial: dict[str, Any] | None = None,
        *,
        active_statuses: set[str] | None = None,
    ) -> tuple[str, tuple[str, dict[str, Any]] | None]:
        """Atomically reserve a job slot unless an active job already exists."""
        statuses = active_statuses or ACTIVE_STATUSES
        with self.lock:
            self._watchdog_locked(time.time())
            active = [
                (job_id, job)
                for job_id, job in self.jobs.items()
                if job.get("status") in statuses
            ]
            if active:
                job_id, job = max(active, key=lambda item: _updated_at(item[1]))
                return "", (job_id, deepcopy(job))
            return self._create_locked(initial), None

    def _create_locked(self, initial: dict[str, Any] | None = None) -> str:
        job_id = self._next_id_locked()
        now = time.time()
        row: dict[str, Any] = {
            "status": "queued",
            "result": None,
            "error": "",
            "cancel": False,
            "created_at": now,
            "updated_at": now,
            "progress": {
                "phase": "queued",
                "current": 0,
                "total": 1,
                "percent": 0,
                "message": "Task queued.",
                "alpha_id": "",
            },
        }
        if initial:
            row.update(_job_safe(initial))
            row.setdefault("created_at", now)
            row["updated_at"] = now
        self.jobs[job_id] = row
        self._prune_locked()
        self._persist_locked()
        return job_id

    def update(self, job_id: str, *, allow_terminal_overwrite: bool = False, **kwargs: Any) -> None:
        with self.lock:
            if job_id not in self.jobs:
                return
            update = _job_safe(kwargs)
            if _reject_watchdog_terminal_update(self.jobs[job_id], update, allow_terminal_overwrite):
                return
            update.setdefault("updated_at", time.time())
            self.jobs[job_id].update(update)
            self._prune_locked()
            self._persist_locked()

    def heartbeat(
        self,
        job_id: str,
        *,
        operation: str,
        heartbeat_count: int,
        source: str,
        heartbeat_at: float | None = None,
    ) -> bool:
        """Record liveness text without extending the watchdog progress clock."""
        with self.lock:
            if job_id not in self.jobs:
                return False
            now = time.time() if heartbeat_at is None else float(heartbeat_at)
            self._watchdog_locked(now, only_job_id=job_id)
            row = self.jobs.get(job_id)
            if not row:
                return False
            status = str(row.get("status") or "").strip().lower()
            if status not in ACTIVE_STATUSES:
                return False
            progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
            message = str(
                progress.get("status_message")
                or progress.get("message")
                or "Async operation is still running."
            )
            next_progress = dict(progress)
            next_progress.update({
                "task_id": job_id,
                "job_id": job_id,
                "operation": operation,
                "phase": str(progress.get("phase") or operation),
                "status_code": "RUNNING",
                "status_message": f"{message} Backend operation is still running.",
                "message": f"{message} Backend operation is still running.",
                "heartbeat": {
                    "count": int(heartbeat_count),
                    "source": source,
                    "updated_at": now,
                },
            })
            update: dict[str, Any] = {
                "status": "stopping" if status == "stopping" else "running",
                "progress": next_progress,
            }
            current_updated_at = row.get("updated_at")
            if current_updated_at not in ("", None):
                update["updated_at"] = current_updated_at
            self.jobs[job_id].update(_job_safe(update))
            self._prune_locked()
            self._persist_locked()
            return True

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            if job_id not in self.jobs:
                return False
            self.jobs[job_id]["cancel"] = True
            if self.jobs[job_id].get("status") in TERMINAL_STATUSES:
                self.jobs[job_id]["updated_at"] = time.time()
                self._persist_locked()
                return True
            self.jobs[job_id]["status"] = "stopping"
            self.jobs[job_id]["updated_at"] = time.time()
            self._persist_locked()
            return True

    def is_cancelled(self, job_id: str) -> bool:
        with self.lock:
            return bool(self.jobs.get(job_id, {}).get("cancel"))

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            self._watchdog_locked(time.time(), only_job_id=job_id)
            value = self.jobs.get(job_id)
            return deepcopy(value) if value else None

    def latest_active(self) -> tuple[str, dict[str, Any]] | None:
        with self.lock:
            self._watchdog_locked(time.time())
            active = [
                (job_id, job)
                for job_id, job in self.jobs.items()
                if job.get("status") in ACTIVE_STATUSES
            ]
            if not active:
                return None
            job_id, job = max(active, key=lambda item: _updated_at(item[1]))
            return job_id, deepcopy(job)

    def latest_any(self) -> tuple[str, dict[str, Any]] | None:
        with self.lock:
            self._watchdog_locked(time.time())
            if not self.jobs:
                return None
            job_id, job = max(self.jobs.items(), key=lambda item: _updated_at(item[1]))
            return job_id, deepcopy(job)

    def all(self, *, limit: int | None = None) -> list[tuple[str, dict[str, Any]]]:
        with self.lock:
            self._watchdog_locked(time.time())
            rows = sorted(self.jobs.items(), key=lambda item: _updated_at(item[1]), reverse=True)
            if limit is not None:
                rows = rows[: max(0, int(limit))]
            return [(job_id, deepcopy(job)) for job_id, job in rows]

    def watchdog_sweep(self, *, now: float | None = None) -> int:
        """Fail active jobs that have stalled or entered an unknown state."""
        with self.lock:
            return self._watchdog_locked(time.time() if now is None else float(now))

    def clear(self, *, persist: bool = False) -> None:
        with self.lock:
            self.jobs.clear()
            if persist:
                self._persist_locked()

    def _load(self) -> None:
        if not self.persistence_path or not self.persistence_path.is_file():
            return
        try:
            size = self.persistence_path.stat().st_size
        except OSError as exc:
            self.last_persist_error = str(exc)
            return
        if size > self.max_load_bytes:
            self.persistence_load_skipped = True
            self.last_persist_error = (
                f"job store file too large to load safely "
                f"({size} bytes > {self.max_load_bytes}); preserved without loading"
            )
            return
        try:
            payload = json.loads(self.persistence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # F-023: record the failure but do NOT set persistence_load_skipped
            # — persistence remains enabled so the corrupted file can be
            # overwritten with valid data on the next job change.
            self.last_persist_error = f"failed to load job store: {exc}"
            return
        raw_jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(raw_jobs, dict):
            return
        now = time.time()
        rows = [
            (str(job_id), row)
            for job_id, row in raw_jobs.items()
            if isinstance(row, dict)
        ]
        if len(rows) > self.max_jobs:
            rows = sorted(rows, key=lambda item: _updated_at(item[1]), reverse=True)[: self.max_jobs]
        for job_id, row in rows:
            if not isinstance(row, dict):
                continue
            clean = _job_safe(row)
            if clean.get("status") in ACTIVE_STATUSES and self.recover_active_as:
                clean["status"] = self.recover_active_as
                clean["cancel"] = False
                clean["error"] = clean.get("error") or DEFAULT_RECOVERY_ERROR
                clean["updated_at"] = now
                clean["progress"] = {
                    **dict(clean.get("progress") or {}),
                    "phase": self.recover_active_as,
                    "percent": 100,
                    "message": clean["error"],
                }
            self.jobs[job_id] = clean
        self._prune_locked()
        self._persist_locked()

    def _next_id_locked(self) -> str:
        pattern = re.compile(rf"^{re.escape(self.job_prefix)}_(\d+)$")
        highest = 0
        for job_id in self.jobs:
            match = pattern.match(job_id)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"{self.job_prefix}_{highest + 1:04d}"

    def _prune_locked(self) -> None:
        if len(self.jobs) <= self.max_jobs:
            return
        ordered = sorted(self.jobs.items(), key=lambda item: _updated_at(item[1]))
        # Phase 1: remove terminal jobs, oldest first.
        for job_id, job in ordered:
            if len(self.jobs) <= self.max_jobs:
                break
            if job.get("status") not in ACTIVE_STATUSES:
                self.jobs.pop(job_id, None)
        # Phase 2: if still over limit, remove completed/failed jobs.
        if len(self.jobs) > self.max_jobs:
            for job_id, job in ordered:
                if len(self.jobs) <= self.max_jobs:
                    break
                if job.get("status") in ("completed", "failed"):
                    self.jobs.pop(job_id, None)

    def _persist_locked(self) -> None:
        if not self.persistence_path:
            return
        # F-023: persistence_load_skipped is NOT permanent. When jobs change,
        # retry writing so the store self-heals after a transient load skip
        # (e.g. operator shrinks/removes the oversized file). The unreadable
        # old data is overwritten with the current in-memory state.
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "updated_at": time.time(),
                "jobs": self.jobs,
            }
            data = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
            tmp_path = self.persistence_path.with_suffix(self.persistence_path.suffix + ".tmp")
            tmp_path.write_text(data, encoding="utf-8")
            os.replace(tmp_path, self.persistence_path)
            self.last_persist_error = ""
            # Reset load-skipped flag after a successful persist.
            self.persistence_load_skipped = False
        except OSError as exc:
            self.last_persist_error = str(exc)

    def _watchdog_locked(self, now: float, *, only_job_id: str | None = None) -> int:
        if self.watchdog_timeout_seconds <= 0:
            return 0
        changed = 0
        for job_id, job in list(self.jobs.items()):
            if only_job_id is not None and job_id != only_job_id:
                continue
            if _watchdog_should_stop(job, now, self.watchdog_timeout_seconds):
                _mark_watchdog_failed(job, now)
                changed += 1
        if changed:
            self._persist_locked()
        return changed
