"""JSONL research records for auditability and calibration."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.models import Candidate, PipelineEvent, utc_now
from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.contracts import (
    assistant_guidance_record,
    backtest_record,
    lifecycle_record,
    strategy_lifecycle_record,
)
from brain_alpha_ops.research.expression_ast import expression_profile_summary
from brain_alpha_ops.research.guidance import ensure_assistant_guidance_digest


logger = logging.getLogger(__name__)
_LOCK_STALE_SECONDS = 120.0
_LOCK_POLL_SECONDS = 0.05
_EXPRESSION_INDEXED_FILES = {
    "candidates.jsonl",
    "lifecycle.jsonl",
    "checks.jsonl",
    "backtests.jsonl",
    "submissions.jsonl",
    "cloud_alphas.jsonl",
}
_RECORD_INDEXED_FILES = {
    "cloud_alphas.jsonl",
    "backtests.jsonl",
}


class ResearchRepository:
    def __init__(self, storage_dir: str = "data"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def save_candidate(self, run_id: str, candidate: Candidate):
        self._append("candidates.jsonl", _with_expression_summary({"run_id": run_id, **candidate.to_dict()}))

    def save_event(self, run_id: str, event: PipelineEvent):
        self._append("events.jsonl", {"run_id": run_id, **event.to_dict()})

    def save_lifecycle_record(self, run_id: str, record: dict[str, Any]):
        self._append("lifecycle.jsonl", _with_expression_summary(lifecycle_record(run_id, record)))

    def save_cloud_alpha(self, record: dict[str, Any]):
        self.merge_cloud_alphas([record])

    def save_check_record(self, record: dict[str, Any]):
        self._append("checks.jsonl", _with_expression_summary({"timestamp": utc_now(), **record}))

    def save_backtest_record(self, run_id: str, record: dict[str, Any]):
        self._append(
            "backtests.jsonl",
            _with_expression_summary(backtest_record(run_id, record)),
        )

    def save_assistant_guidance(self, guidance: dict[str, Any], *, source: str = "web") -> None:
        guidance = ensure_assistant_guidance_digest(guidance)
        self._append("assistant_guidance.jsonl", assistant_guidance_record(guidance, source=source))

    def save_strategy_lifecycle_record(self, run_id: str, record: dict[str, Any]) -> None:
        self._append("strategy_lifecycle.jsonl", strategy_lifecycle_record(run_id, record))

    def save_run_history(self, run_id: str, result: dict[str, Any], *, status: str = "completed") -> Path:
        """Persist the latest run snapshot for UI recovery after app restart."""
        history_dir = Path(self.storage_dir) / "run_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            **(result or {}),
            "run_id": run_id,
            "status": status,
            "timestamp": utc_now(),
        }
        payload = _repository_safe(payload)
        with self._file_lock("run_history"):
            target = history_dir / f"{run_id}.json"
            latest = history_dir / "latest.json"
            tmp = history_dir / f".{run_id}.{os.getpid()}.{time.time_ns()}.tmp"
            data = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            tmp.write_text(data, encoding="utf-8")
            tmp.replace(target)
            latest_tmp = history_dir / f".latest.{os.getpid()}.{time.time_ns()}.tmp"
            latest_tmp.write_text(data, encoding="utf-8")
            latest_tmp.replace(latest)
            return target

    def cloud_alpha_ids(self) -> set[str]:
        return set(self._latest_cloud_alpha_rows().keys())

    def latest_cloud_alphas(self) -> list[dict[str, Any]]:
        return list(self._latest_cloud_alpha_rows().values())

    def latest_backtest_records(self, *, limit: int = 500) -> list[dict[str, Any]]:
        return read_jsonl_tail(Path(self.storage_dir) / "backtests.jsonl", limit=max(1, int(limit or 1)))

    def merge_cloud_alphas(self, rows: list[dict[str, Any]], *, sync_range: str = "") -> dict[str, int]:
        """Append only new or changed cloud Alpha records.

        The cloud cache is an append-only history.  A record is appended when
        its alpha id has not been seen before, or when the latest stored
        version has a different stable hash.  This preserves incremental
        changes without rewriting the whole file.
        """
        stats = {"scanned": 0, "added": 0, "updated": 0, "skipped": 0, "failed": 0}
        if not rows:
            return stats
        filename = "cloud_alphas.jsonl"
        with self._file_lock(filename):
            latest_by_id = self._latest_cloud_alpha_rows_unlocked()
            seen_hashes = {
                str(row.get("cloud_record_hash") or _cloud_record_hash(row))
                for row in latest_by_id.values()
            }
            for row in rows:
                stats["scanned"] += 1
                if not isinstance(row, dict):
                    stats["failed"] += 1
                    continue
                clean_row = _repository_safe(row)
                alpha_id = _cloud_alpha_id(clean_row)
                record_hash = _cloud_record_hash(clean_row)
                existing = latest_by_id.get(alpha_id) if alpha_id else None
                existing_hash = str((existing or {}).get("cloud_record_hash") or (_cloud_record_hash(existing) if existing else ""))
                if alpha_id and existing and existing_hash == record_hash:
                    stats["skipped"] += 1
                    continue
                if not alpha_id and record_hash in seen_hashes:
                    stats["skipped"] += 1
                    continue

                now = utc_now()
                record = {
                    **clean_row,
                    "timestamp": now,
                    "synced_at": now,
                    "sync_range": sync_range,
                    "cloud_record_hash": record_hash,
                }
                self._append_unlocked(filename, record)
                if alpha_id:
                    latest_by_id[alpha_id] = record
                    if existing:
                        stats["updated"] += 1
                    else:
                        stats["added"] += 1
                else:
                    seen_hashes.add(record_hash)
                    stats["added"] += 1
        return stats

    def _latest_cloud_alpha_rows(self) -> dict[str, dict[str, Any]]:
        with self._file_lock("cloud_alphas.jsonl"):
            return self._latest_cloud_alpha_rows_unlocked()

    def _latest_cloud_alpha_rows_unlocked(self) -> dict[str, dict[str, Any]]:
        path = os.path.join(self.storage_dir, "cloud_alphas.jsonl")
        latest: dict[str, dict[str, Any]] = {}
        if not os.path.exists(path):
            return latest
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    alpha_id = _cloud_alpha_id(record)
                    if alpha_id:
                        latest[alpha_id] = record
        except OSError:
            return latest
        return latest

    def save_family_record(self, candidate: Candidate):
        self._append(
            "families.jsonl",
            {
                "timestamp": utc_now(),
                "family": candidate.family,
                "alpha_id": candidate.alpha_id,
                "parent_id": candidate.parent_id,
                "mutation_type": candidate.mutation_type,
                "status": candidate.lifecycle_status,
                "score": candidate.scorecard.get("total_score"),
                "correlation": (candidate.official_metrics or {}).get("correlation"),
            },
        )

    def maybe_archive(self, filename: str, max_size_mb: int = 50, max_age_days: int = 30):
        """C4: Archive large JSONL files when they exceed max_size_mb.

        Renames the current file to a timestamped archive and cleans up
        archives older than max_age_days.
        """
        from datetime import datetime, timedelta
        from pathlib import Path

        with self._file_lock(filename):
            path = Path(self.storage_dir) / filename
            if not path.is_file():
                return
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb <= max_size_mb:
                return

            suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = Path(self.storage_dir) / f"{Path(filename).stem}_{suffix}.jsonl"
            try:
                path.rename(archive_path)
            except OSError:
                return

        # Clean up old archives
        cutoff = datetime.now() - timedelta(days=max_age_days)
        stem = Path(filename).stem
        for old in sorted(Path(self.storage_dir).glob(f"{stem}_*.jsonl")):
            try:
                mtime = datetime.fromtimestamp(old.stat().st_mtime)
                if mtime < cutoff:
                    old.unlink()
            except OSError:
                continue

    def save_ab_test(self, run_id: str, before: dict[str, Any], after: dict[str, Any], only_changed: str):
        self._append(
            "ab_tests.jsonl",
            {
                "timestamp": utc_now(),
                "run_id": run_id,
                "only_changed": only_changed,
                "before": before,
                "after": after,
            },
        )

    def _append(self, filename: str, record: dict[str, Any]):
        with self._file_lock(filename):
            self._append_unlocked(filename, record)

    def _append_unlocked(self, filename: str, record: dict[str, Any]):
        record = _repository_safe(record)
        with open(os.path.join(self.storage_dir, filename), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._update_expression_sqlite_cache(filename, record)
        self._update_record_sqlite_cache(filename, record)

    def _file_lock(self, filename: str):
        return _RepositoryFileLock(os.path.join(self.storage_dir, f"{filename}.lock"))

    def _update_expression_sqlite_cache(self, filename: str, record: dict[str, Any]) -> None:
        if filename not in _EXPRESSION_INDEXED_FILES:
            return
        try:
            from brain_alpha_ops.research.expression_sqlite_index import ExpressionSqliteIndex

            ExpressionSqliteIndex(self.storage_dir).append_record(record, source_file=filename)
        except Exception as exc:
            logger.debug(
                "failed to update incremental expression sqlite cache for %s: %s",
                filename,
                exc,
                exc_info=True,
            )

    def _update_record_sqlite_cache(self, filename: str, record: dict[str, Any]) -> None:
        if filename not in _RECORD_INDEXED_FILES:
            return
        try:
            from brain_alpha_ops.research.record_sqlite_index import RecordSqliteIndex

            RecordSqliteIndex(self.storage_dir).append_record(record, source_file=filename)
        except Exception as exc:
            logger.debug(
                "failed to update incremental record sqlite cache for %s: %s",
                filename,
                exc,
                exc_info=True,
            )


class _RepositoryFileLock:
    def __init__(self, lock_path: str, timeout_seconds: float = 30.0):
        self.lock_path = lock_path
        self.timeout_seconds = timeout_seconds
        self.fd: int | None = None

    def __enter__(self):
        deadline = time.time() + self.timeout_seconds
        while True:
            try:
                self.fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(self.fd, f"{os.getpid()} {time.time()}".encode("ascii"))
                return self
            except FileExistsError:
                self._remove_stale_lock()
                if time.time() >= deadline:
                    raise TimeoutError(f"timed out waiting for repository lock: {self.lock_path}")
                time.sleep(_LOCK_POLL_SECONDS)

    def __exit__(self, _exc_type, _exc, _tb):
        if self.fd is not None:
            try:
                os.close(self.fd)
            finally:
                self.fd = None
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass

    def _remove_stale_lock(self) -> None:
        try:
            age = time.time() - os.path.getmtime(self.lock_path)
        except OSError:
            return
        if age > _LOCK_STALE_SECONDS:
            try:
                os.unlink(self.lock_path)
            except OSError:
                pass


def _cloud_alpha_id(row: dict[str, Any] | None) -> str:
    row = row or {}
    return str(row.get("id") or row.get("alpha_id") or "")


def _cloud_record_hash(row: dict[str, Any] | None) -> str:
    row = row or {}
    volatile = {"timestamp", "synced_at", "sync_range", "cloud_record_hash"}
    stable = {key: value for key, value in row.items() if key not in volatile}
    payload = json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _with_expression_summary(record: dict[str, Any]) -> dict[str, Any]:
    expression = str(record.get("expression") or "")
    if not expression:
        candidate = record.get("candidate")
        if isinstance(candidate, dict):
            expression = str(candidate.get("expression") or "")
    if not expression:
        return record
    return {**record, **expression_profile_summary(expression)}


def _repository_safe(record: dict[str, Any]) -> dict[str, Any]:
    clean = redact_data(record)
    return clean if isinstance(clean, dict) else {}
