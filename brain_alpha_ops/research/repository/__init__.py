"""JSONL research records for auditability and calibration.

This package is a pure mechanical split of the original
``brain_alpha_ops/research/repository.py`` module.  The public API and all
module-level symbols remain importable from ``brain_alpha_ops.research.repository``
exactly as before.
"""

from __future__ import annotations

import logging

from brain_alpha_ops.research.repository._cloud_mixin import ResearchRepositoryCloudMixin
from brain_alpha_ops.research.repository._constants import (
    _EXPRESSION_INDEXED_FILES,
    _LOCK_POLL_SECONDS,
    _LOCK_STALE_SECONDS,
    _RECORD_INDEXED_FILES,
    _REPOSITORY_JSONL_FILES,
    _REPOSITORY_LOCK_NAMES,
    _SQLITE_INDEX_DIAGNOSTICS_FILE,
    _cloud_alpha_id,
    _cloud_record_hash,
    _ensure_contained,
    _repository_safe,
    _with_expression_summary,
)
from brain_alpha_ops.research.repository._core_mixin import ResearchRepositoryCoreMixin
from brain_alpha_ops.research.repository._file_lock import _RepositoryFileLock
from brain_alpha_ops.research.repository._sqlite_mixin import ResearchRepositorySqliteMixin
from brain_alpha_ops.research.repository._writes_mixin import ResearchRepositoryWritesMixin

# Hardcoded logger name to preserve the original module's logger identity
# (originally ``logging.getLogger(__name__)`` where __name__ resolved to
# ``brain_alpha_ops.research.repository``).  Tests assert on this exact name.
logger = logging.getLogger("brain_alpha_ops.research.repository")


class ResearchRepository(ResearchRepositorySqliteMixin):
    """Append-only JSONL research store with SQLite incremental indexes."""


__all__ = ["ResearchRepository"]
