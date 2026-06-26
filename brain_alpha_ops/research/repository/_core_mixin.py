"""Core infrastructure mixin for ``ResearchRepository``.

Holds construction, path validation, file-lock acquisition, and the low-level
append helper shared by all the higher-level repository mixins.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from brain_alpha_ops.research.repository._constants import (
    _REPOSITORY_JSONL_FILES,
    _REPOSITORY_LOCK_NAMES,
    _ensure_contained,
    _repository_safe,
)
from brain_alpha_ops.research.repository._file_lock import _RepositoryFileLock


class ResearchRepositoryCoreMixin:
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
