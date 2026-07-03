"""Repository foundation: constants, helpers, file-lock, and core mixin.

Merged from the former ``_constants``, ``_file_lock``, and ``_core_mixin``
sub-modules.  This is the foundation layer of the research repository
package — it holds the module-level constants, helper functions, the
exclusive file-lock primitive, and the core infrastructure mixin
(``ResearchRepositoryCoreMixin``) that all higher-level repository mixins
build upon.

Higher-level mixins (writes / cloud / sqlite) live in ``repository_mixins``
and import ``ResearchRepositoryCoreMixin`` and the constants/helpers from
here, preserving a one-way dependency: ``repository_mixins`` → ``repository``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.expression_ast import expression_profile_summary

# Hardcoded logger name to preserve the original module's logger identity
# (originally ``logging.getLogger(__name__)`` where __name__ was
# ``brain_alpha_ops.research.repository``).
logger = logging.getLogger("brain_alpha_ops.research.repository")


# ── Module-level constants ────────────────────────────────────────────────


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
_SQLITE_INDEX_DIAGNOSTICS_FILE = "sqlite_index_diagnostics.jsonl"
_REPOSITORY_JSONL_FILES = _EXPRESSION_INDEXED_FILES | _RECORD_INDEXED_FILES | {
    "ab_tests.jsonl",
    "assistant_guidance.jsonl",
    "events.jsonl",
    "families.jsonl",
    _SQLITE_INDEX_DIAGNOSTICS_FILE,
    "strategy_lifecycle.jsonl",
}
_REPOSITORY_LOCK_NAMES = _REPOSITORY_JSONL_FILES | {"run_history"}


# ── Helper functions ──────────────────────────────────────────────────────


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


def _ensure_contained(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"repository path escapes storage root: {path}") from None


# ── Exclusive file-lock primitive ─────────────────────────────────────────


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


# ── Core infrastructure mixin ─────────────────────────────────────────────


class ResearchRepositoryCoreMixin:
    """Construction, path validation, file-lock acquisition, and the low-level
    append helper shared by all the higher-level repository mixins.
    """

    def __init__(self, storage_dir: str = "data"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def _append(self, filename: str, record: dict[str, Any]):
        with self._file_lock(filename):
            self._append_unlocked(filename, record)

    def _append_unlocked(self, filename: str, record: dict[str, Any]):
        path = self._safe_storage_path(filename)
        record = _repository_safe(record)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._update_expression_sqlite_cache(filename, record)
        self._update_record_sqlite_cache(filename, record)

    def _file_lock(self, filename: str):
        return _RepositoryFileLock(str(self._safe_lock_path(filename)))

    def _storage_root(self) -> Path:
        return Path(self.storage_dir).expanduser().resolve()

    def _safe_storage_path(self, filename: str) -> Path:
        if filename not in _REPOSITORY_JSONL_FILES:
            raise ValueError(f"unsupported repository JSONL file: {filename}")
        if Path(filename).name != filename or Path(filename).is_absolute():
            raise ValueError(f"unsafe repository JSONL file: {filename}")
        path = (self._storage_root() / filename).resolve()
        _ensure_contained(path, self._storage_root())
        return path

    def _safe_lock_path(self, filename: str) -> Path:
        if filename not in _REPOSITORY_LOCK_NAMES:
            raise ValueError(f"unsupported repository lock target: {filename}")
        if Path(filename).name != filename or Path(filename).is_absolute():
            raise ValueError(f"unsafe repository lock target: {filename}")
        path = (self._storage_root() / f"{filename}.lock").resolve()
        _ensure_contained(path, self._storage_root())
        return path

    def _safe_archive_path(self, filename: str, suffix: str) -> Path:
        path = (self._storage_root() / f"{Path(filename).stem}_{suffix}.jsonl").resolve()
        _ensure_contained(path, self._storage_root())
        return path
