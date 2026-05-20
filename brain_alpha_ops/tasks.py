"""Reusable task state storage for long-running operations.

The web console, future agent tools, and any CLI orchestration should share the
same small contract for job lifecycle state. The store intentionally keeps the
runtime payload narrow: status, progress, result, cancellation flag, and error.
It never persists request credentials.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any

from brain_alpha_ops.redaction import redact_data


ACTIVE_STATUSES = {"queued", "running", "stopping"}
DEFAULT_RECOVERY_ERROR = "Process restarted before this task completed."


class JobStore:
    """Thread-safe job state store with optional JSON persistence."""

    def __init__(
        self,
        persistence_path: str | Path | None = None,
        *,
        job_prefix: str = "job",
        max_jobs: int = 200,
        recover_active_as: str = "failed",
    ):
        self.lock = threading.Lock()
        self.jobs: dict[str, dict[str, Any]] = {}
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self.job_prefix = job_prefix or "job"
        self.max_jobs = max(1, int(max_jobs or 1))
        self.recover_active_as = recover_active_as
        self.last_persist_error = ""
        self._load()

    def create(self, initial: dict[str, Any] | None = None) -> str:
        with self.lock:
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

    def update(self, job_id: str, **kwargs: Any) -> None:
        with self.lock:
            if job_id not in self.jobs:
                return
            update = _job_safe(kwargs)
            update.setdefault("updated_at", time.time())
            self.jobs[job_id].update(update)
            self._prune_locked()
            self._persist_locked()

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            if job_id not in self.jobs:
                return False
            self.jobs[job_id]["cancel"] = True
            self.jobs[job_id]["status"] = "stopping"
            self.jobs[job_id]["updated_at"] = time.time()
            self._persist_locked()
            return True

    def is_cancelled(self, job_id: str) -> bool:
        with self.lock:
            return bool(self.jobs.get(job_id, {}).get("cancel"))

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            value = self.jobs.get(job_id)
            return deepcopy(value) if value else None

    def latest_active(self) -> tuple[str, dict[str, Any]] | None:
        with self.lock:
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
            if not self.jobs:
                return None
            job_id, job = max(self.jobs.items(), key=lambda item: _updated_at(item[1]))
            return job_id, deepcopy(job)

    def all(self, *, limit: int | None = None) -> list[tuple[str, dict[str, Any]]]:
        with self.lock:
            rows = sorted(self.jobs.items(), key=lambda item: _updated_at(item[1]), reverse=True)
            if limit is not None:
                rows = rows[: max(0, int(limit))]
            return [(job_id, deepcopy(job)) for job_id, job in rows]

    def _load(self) -> None:
        if not self.persistence_path or not self.persistence_path.is_file():
            return
        try:
            payload = json.loads(self.persistence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        raw_jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(raw_jobs, dict):
            return
        now = time.time()
        for job_id, row in raw_jobs.items():
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
            self.jobs[str(job_id)] = clean
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
        for job_id, job in ordered:
            if len(self.jobs) <= self.max_jobs:
                break
            if job.get("status") not in ACTIVE_STATUSES:
                self.jobs.pop(job_id, None)
        for job_id, _job in ordered:
            if len(self.jobs) <= self.max_jobs:
                break
            self.jobs.pop(job_id, None)

    def _persist_locked(self) -> None:
        if not self.persistence_path:
            return
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
        except OSError as exc:
            self.last_persist_error = str(exc)


def _updated_at(job: dict[str, Any]) -> float:
    try:
        return float(job.get("updated_at", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _job_safe(value: Any) -> Any:
    return redact_data(_json_safe(value))
