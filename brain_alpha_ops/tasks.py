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
JOB_PREVIEW_ROWS = 5
COMPACT_LIST_KEYS = {"alphas", "cloud_alphas", "candidates", "backtests", "lifecycle_records"}


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

    def clear(self, *, persist: bool = False) -> None:
        with self.lock:
            self.jobs.clear()
            if persist:
                self._persist_locked()

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
