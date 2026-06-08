"""Async job management for the BRAIN Alpha Ops web console.

Extracted from web.py to separate job management from server infrastructure.

Persistence: jobs are stored in-memory (ASYNC_JOBS) with optional JSONL backup
for cross-restart recovery. When a storage directory is configured, every job update
is also appended to a JSONL file so running/failed jobs survive service restarts.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_data, redact_error_message
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ═══════════════════════ Job Storage ══════════════════════════════════
ASYNC_JOBS: dict[str, dict] = {}
ASYNC_JOBS_LOCK = threading.RLock()

# Job lifecycle constants
_ASYNC_JOB_MAX_AGE_SECONDS = 3600  # 1 hour TTL for completed/failed jobs
_ASYNC_JOB_MAX_COUNT = 200  # hard cap on total jobs in memory
_ASYNC_JOB_TERMINAL_STATUSES = frozenset({
    "completed", "completed_with_warnings", "failed", "stopped", "cancelled", "canceled",
})

# ── JSONL persistence ──
_JOBS_JSONL_DIR: str = ""
_JOBS_JSONL_FILENAME = "web_jobs.jsonl"
_JOBS_JSONL_PATH: Path | None = None


# ═══════════════════════ Job ID Generation ════════════════════════════
def new_job_id(prefix: str = "job") -> str:
    """Generate a new unique job ID."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ═══════════════════════ Timestamp Helpers ════════════════════════════
def utc_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════ Job CRUD Operations ══════════════════════════
# ═══════════════════════ JSONL Persistence ════════════════════════════

def set_jobs_storage_dir(storage_dir: str) -> None:
    """Configure the directory used for JSONL job persistence.

    Call once during server startup so jobs survive restarts.
    """
    global _JOBS_JSONL_DIR, _JOBS_JSONL_PATH
    _JOBS_JSONL_DIR = storage_dir
    _JOBS_JSONL_PATH = Path(storage_dir) / _JOBS_JSONL_FILENAME if storage_dir else None


def _persist_job_to_jsonl(row: dict) -> None:
    """Append a single job snapshot to the JSONL file (best-effort)."""
    path = _JOBS_JSONL_PATH
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        logger.debug("Failed to persist job %s to JSONL: %s", row.get("job_id", ""), redact_error_message(exc))


def load_jobs_from_jsonl() -> int:
    """Load previously persisted jobs from JSONL into memory.

    Only restores non-terminal jobs (running/pending/starting).
    Returns the number of restored jobs.
    """
    path = _JOBS_JSONL_PATH
    if not path or not path.is_file():
        return 0
    restored = 0
    latest_by_id: dict[str, dict] = {}
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                jid = str(row.get("job_id") or "")
                if not jid:
                    continue
                # Keep only the last snapshot per job_id (JSONL is append-only)
                latest_by_id[jid] = _job_safe(row)
    except OSError as exc:
        logger.warning("Failed to read job persistence file: %s", redact_error_message(exc))
        return 0
    with ASYNC_JOBS_LOCK:
        for jid, row in latest_by_id.items():
            status = str(row.get("status", "")).lower()
            if status in _ASYNC_JOB_TERMINAL_STATUSES:
                continue  # don't restore finished/cancelled jobs
            if jid not in ASYNC_JOBS:
                ASYNC_JOBS[jid] = row
                restored += 1
    if restored:
        logger.info("Restored %d non-terminal job(s) from JSONL persistence", restored)
    return restored


def init_job_persistence(storage_dir: str = "") -> int:
    """Convenience: set storage dir and load persisted jobs.

    Call once during web server startup. Passing an empty string disables persistence.
    """
    if storage_dir:
        set_jobs_storage_dir(storage_dir)
    return load_jobs_from_jsonl()


def job_update(job_id: str, **fields: Any) -> dict:
    """Update job fields and return the updated job row."""
    with ASYNC_JOBS_LOCK:
        row = dict(ASYNC_JOBS.get(job_id) or {})
        row.update(fields)
        row["job_id"] = job_id
        row["task_id"] = job_id
        row["updated_at"] = utc_timestamp()
        row = _job_safe(row)
        ASYNC_JOBS[job_id] = row
        _prune_async_jobs()
        result = dict(row)
    # Persist outside the lock to avoid I/O contention
    _persist_job_to_jsonl(result)
    return result


def _job_safe(row: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-serializable job row with credentials redacted."""
    safe = redact_data(row)
    return safe if isinstance(safe, dict) else {}


def job_get(job_id: str) -> dict | None:
    """Get job by ID."""
    with ASYNC_JOBS_LOCK:
        row = ASYNC_JOBS.get(job_id)
        return dict(row) if isinstance(row, dict) else None


def job_list(*, status: str | None = None, limit: int = 100) -> list[dict]:
    """List jobs, optionally filtered by status."""
    with ASYNC_JOBS_LOCK:
        jobs = list(ASYNC_JOBS.values())
    if status:
        jobs = [j for j in jobs if str(j.get("status", "")).lower() == status.lower()]
    jobs.sort(key=lambda j: str(j.get("updated_at", "")), reverse=True)
    return jobs[:limit]


def job_delete(job_id: str) -> bool:
    """Delete a job by ID."""
    with ASYNC_JOBS_LOCK:
        if job_id in ASYNC_JOBS:
            del ASYNC_JOBS[job_id]
            return True
        return False


# ═══════════════════════ Job Lifecycle Management ═════════════════════
def job_start(job_id: str, **extra: Any) -> dict:
    """Mark job as running."""
    return job_update(job_id, status="running", **extra)


def job_progress(job_id: str, *, phase: str = "", percent: int = 0, message: str = "", **extra: Any) -> dict:
    """Update job progress."""
    return job_update(
        job_id,
        status="running",
        progress={
            "phase": phase,
            "percent_complete": percent,
            "status_message": message,
        },
        **extra,
    )


def job_complete(job_id: str, result: Any = None, **extra: Any) -> dict:
    """Mark job as completed."""
    return job_update(job_id, status="completed", result=result, **extra)


def job_fail(job_id: str, error: str, **extra: Any) -> dict:
    """Mark job as failed."""
    return job_update(job_id, status="failed", error=error, **extra)


def job_cancel(job_id: str, **extra: Any) -> dict:
    """Mark job as cancelled."""
    return job_update(job_id, status="cancelled", **extra)


def is_cancelled(job_id: str) -> bool:
    """Check if a job has been cancelled or stopped."""
    with ASYNC_JOBS_LOCK:
        row = ASYNC_JOBS.get(job_id)
    if not isinstance(row, dict):
        return False
    return str(row.get("status", "")).lower() in {"cancelled", "canceled", "stopped"}


# ═══════════════════════ Job Pruning ══════════════════════════════════
def _prune_async_jobs() -> None:
    """Remove expired terminal jobs and enforce max count."""
    if not ASYNC_JOBS:
        return
    now = time.time()
    expired_ids: list[str] = []
    for job_id, row in ASYNC_JOBS.items():
        status = str(row.get("status", "")).lower()
        updated_at = str(row.get("updated_at", ""))
        if status in _ASYNC_JOB_TERMINAL_STATUSES:
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp()
            except (ValueError, AttributeError):
                ts = 0.0
            if now - ts > _ASYNC_JOB_MAX_AGE_SECONDS:
                expired_ids.append(job_id)
    for jid in expired_ids:
        ASYNC_JOBS.pop(jid, None)
    # Hard cap: remove oldest terminal jobs if over limit
    while len(ASYNC_JOBS) > _ASYNC_JOB_MAX_COUNT:
        terminal = [(jid, r) for jid, r in ASYNC_JOBS.items()
                     if str(r.get("status", "")).lower() in _ASYNC_JOB_TERMINAL_STATUSES]
        if not terminal:
            break
        oldest = min(terminal, key=lambda x: str(x[1].get("updated_at", "")))
        ASYNC_JOBS.pop(oldest[0], None)


def prune_jobs() -> int:
    """Manually trigger job pruning and return number of pruned jobs."""
    with ASYNC_JOBS_LOCK:
        before = len(ASYNC_JOBS)
        _prune_async_jobs()
        return before - len(ASYNC_JOBS)


# ═══════════════════════ Job Statistics ═══════════════════════════════
def job_stats() -> dict:
    """Get job statistics."""
    with ASYNC_JOBS_LOCK:
        total = len(ASYNC_JOBS)
        by_status: dict[str, int] = {}
        for row in ASYNC_JOBS.values():
            status = str(row.get("status", "unknown")).lower()
            by_status[status] = by_status.get(status, 0) + 1
    return {
        "total": total,
        "by_status": by_status,
        "max_age_seconds": _ASYNC_JOB_MAX_AGE_SECONDS,
        "max_count": _ASYNC_JOB_MAX_COUNT,
    }


# ═══════════════════════ Job Search ═══════════════════════════════════
def job_search(query: str, *, limit: int = 10) -> list[dict]:
    """Search jobs by ID or status."""
    query_lower = query.lower()
    with ASYNC_JOBS_LOCK:
        matches = []
        for row in ASYNC_JOBS.values():
            if (query_lower in str(row.get("job_id", "")).lower() or
                query_lower in str(row.get("status", "")).lower()):
                matches.append(dict(row))
    matches.sort(key=lambda j: str(j.get("updated_at", "")), reverse=True)
    return matches[:limit]
