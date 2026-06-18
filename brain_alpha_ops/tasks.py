"""Reusable task state storage for long-running operations (pipeline jobs).

**Purpose**: Persist pipeline background jobs (production, sync, check,
async) with thread-safe state, watchdog, and atomic JSON persistence.

**Relationship to web_jobs.py**: This module tracks *pipeline* background
jobs; ``brain_alpha_ops.web_jobs`` tracks *Web UI* user operations.  They
serve different lifecycles and should NOT be unified (P1-7 clarification).
See ``web_jobs.get_web_job_store()`` for the Protocol-based bridge that
allows background services to use web_jobs without a full JobStore.



The web console and internal automation share the same small contract for job
lifecycle state. The store intentionally keeps the
runtime payload narrow: status, progress, result, cancellation flag, and error.
It never persists request credentials.
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

from brain_alpha_ops.core_state import (
    JOB_ACTIVE_STATUSES as ACTIVE_STATUSES,
)
from brain_alpha_ops.core_state import (
    JOB_KNOWN_STATUSES as KNOWN_STATUSES,
)
from brain_alpha_ops.core_state import (
    JOB_TERMINAL_STATUSES as TERMINAL_STATUSES,
)
from brain_alpha_ops.core_state import (
    is_active_job_status,
    is_terminal_job_status,
)
from brain_alpha_ops.redaction import redact_data

DEFAULT_RECOVERY_ERROR = "Process restarted before this task completed."
DEFAULT_WATCHDOG_TIMEOUT_SECONDS = 300.0
DEFAULT_WATCHDOG_ERROR = "Web flow watchdog stopped this task after no clear progress update."
JOB_PREVIEW_ROWS = 5
COMPACT_LIST_KEYS = {"alphas", "cloud_alphas", "candidates", "backtests", "lifecycle_records"}
DEFAULT_MAX_PERSISTENCE_LOAD_BYTES = 50 * 1024 * 1024

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
        """Fail active jobs that have stalled or entered an unknown state.

        The Web UI polls job status as the user operates the console. Running
        the sweep on reads turns ambiguous hangs into explicit, user-visible
        failure states without using tests to tune Alpha expressions.
        """
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
        except (OSError, json.JSONDecodeError):
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
        # Phase 1: remove non-active (terminal) jobs, oldest first.
        for job_id, job in ordered:
            if len(self.jobs) <= self.max_jobs:
                break
            if job.get("status") not in ACTIVE_STATUSES:
                self.jobs.pop(job_id, None)
        # Phase 2: if still over the limit, only remove long-completed jobs
        # (status completed / failed) rather than active ones.
        if len(self.jobs) > self.max_jobs:
            for job_id, job in ordered:
                if len(self.jobs) <= self.max_jobs:
                    break
                if job.get("status") in ("completed", "failed"):
                    self.jobs.pop(job_id, None)

    def _persist_locked(self) -> None:
        if not self.persistence_path:
            return
        if self.persistence_load_skipped:
            self.last_persist_error = self.last_persist_error or "job store persistence skipped after oversized load"
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

def _updated_at(job: dict[str, Any]) -> float:
    try:
        return float(job.get("updated_at", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0

def _watchdog_should_stop(job: dict[str, Any], now: float, timeout_seconds: float) -> bool:
    status = str(job.get("status") or "").strip().lower()
    if status in TERMINAL_STATUSES:
        return False
    if status not in ACTIVE_STATUSES:
        return True
    updated_at = _updated_at(job)
    return updated_at <= 0 or now - updated_at > timeout_seconds

def _mark_watchdog_failed(job: dict[str, Any], now: float) -> None:
    status = str(job.get("status") or "unknown").strip().lower() or "unknown"
    message = (
        "Web flow watchdog stopped this task because its status was unclear."
        if status not in ACTIVE_STATUSES
        else DEFAULT_WATCHDOG_ERROR
    )
    job["status"] = "failed"
    job["cancel"] = True
    job["error"] = message
    job["updated_at"] = now
    progress = dict(job.get("progress") or {})
    progress.update({
        "phase": "watchdog_failed",
        "percent": 100,
        "percent_complete": 100,
        "message": message,
        "status_message": message,
        "watchdog": {
            "triggered": True,
            "previous_status": status,
        },
    })
    job["progress"] = progress

def _reject_watchdog_terminal_update(
    current: dict[str, Any],
    update: dict[str, Any],
    allow_terminal_overwrite: bool,
) -> bool:
    if allow_terminal_overwrite or not _is_watchdog_terminal_failed(current):
        return False
    return True

def _is_watchdog_terminal_failed(job: dict[str, Any]) -> bool:
    if str(job.get("status") or "").strip().lower() != "failed":
        return False
    progress = job.get("progress") if isinstance(job.get("progress"), dict) else {}
    watchdog = progress.get("watchdog") if isinstance(progress.get("watchdog"), dict) else {}
    return progress.get("phase") == "watchdog_failed" or watchdog.get("triggered") is True

def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))

def _compact_runtime_result(value: Any, *, preview_rows: int = JOB_PREVIEW_ROWS) -> Any:
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            if _should_compact_named_list(key, item):
                compact[f"{key}_count"] = len(item)
                compact[f"{key}_preview"] = [_compact_runtime_result(row, preview_rows=preview_rows) for row in item[:preview_rows]]
                evidence = _submission_evidence_rows(item, preview_rows=preview_rows)
                if evidence:
                    compact[f"{key}_submission_evidence"] = evidence
                continue
            compact[key] = _compact_runtime_result(item, preview_rows=preview_rows)
        return compact
    if isinstance(value, list):
        if len(value) > preview_rows:
            return {
                "items_count": len(value),
                "items_preview": [_compact_runtime_result(item, preview_rows=preview_rows) for item in value[:preview_rows]],
            }
        return [_compact_runtime_result(item, preview_rows=preview_rows) for item in value]
    return value

def _should_compact_named_list(key: str, item: Any) -> bool:
    if not isinstance(item, list):
        return False
    return key in COMPACT_LIST_KEYS or key.endswith("candidates")

def _submission_evidence_rows(items: list[Any], *, preview_rows: int) -> list[Any]:
    evidence: list[Any] = []
    hidden_start = max(0, int(preview_rows or 0))
    seen: set[str] = {
        _submission_evidence_key(item)
        for item in items[:hidden_start]
        if isinstance(item, dict)
    }
    for item in items[hidden_start:]:
        if not isinstance(item, dict):
            continue
        compact = _candidate_submission_audit_evidence(item, preview_rows=preview_rows)
        key = _submission_evidence_key(compact)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(compact)
    return evidence

def _candidate_submission_audit_evidence(candidate: dict[str, Any], *, preview_rows: int) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for key in (
        "alpha_id",
        "official_alpha_id",
        "simulation_id",
        "expression",
        "family",
        "hypothesis",
        "dataset_id",
        "data_fields",
        "operators",
        "alpha_output_config",
        "quality_diagnosis",
        "local_quality",
        "source_tags",
        "lifecycle_status",
        "decision_band",
        "score",
    ):
        if key in candidate:
            evidence[key] = candidate[key]
    for key, nested_keys in (
        ("scorecard", ("total_score", "decision_band", "status", "hard_gate_failed")),
        ("gate", ("submission_ready", "status", "blocking_reasons")),
        (
            "official_metrics",
            (
                "official_alpha_id",
                "pass_fail",
                "sharpe",
                "fitness",
                "turnover",
                "returns",
                "drawdown",
                "correlation",
                "prod_correlation",
            ),
        ),
        (
            "metrics",
            (
                "official_alpha_id",
                "pass_fail",
                "sharpe",
                "fitness",
                "turnover",
                "returns",
                "drawdown",
                "correlation",
                "prod_correlation",
            ),
        ),
        ("cloud_correlation_risk", ("level", "max_similarity", "status", "matched_alpha_id", "matched_expression")),
    ):
        nested = candidate.get(key) if isinstance(candidate.get(key), dict) else {}
        if nested:
            evidence[key] = {
                nested_key: nested[nested_key]
                for nested_key in nested_keys
                if nested_key in nested
            }
    submission = candidate.get("submission") if isinstance(candidate.get("submission"), dict) else {}
    local_backtest = submission.get("local_backtest") if isinstance(submission.get("local_backtest"), dict) else {}
    if local_backtest:
        evidence["submission"] = {
            "local_backtest": {
                key: local_backtest[key]
                for key in ("pass_local", "reasons", "diagnostics")
                if key in local_backtest
            }
        }
    return _compact_runtime_result(evidence, preview_rows=preview_rows)

def _submission_evidence_key(candidate: Any) -> str:
    if not isinstance(candidate, dict):
        return str(id(candidate))
    return str(
        candidate.get("alpha_id")
        or candidate.get("official_alpha_id")
        or candidate.get("simulation_id")
        or candidate.get("expression")
        or id(candidate)
    )

def _job_safe(value: Any) -> Any:
    safe = _json_safe(value)
    if isinstance(safe, dict) and "result" in safe:
        safe = dict(safe)
        safe["result"] = _compact_runtime_result(safe.get("result"))
    return redact_data(safe)
