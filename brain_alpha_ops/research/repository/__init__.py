"""JSONL research records for auditability and calibration.

This package is a pure mechanical split of the original
``brain_alpha_ops/research/repository.py`` module.  The public API and all
module-level symbols remain importable from ``brain_alpha_ops.research.repository``
exactly as before.

The package is physically organised into two cohesive modules:
  - ``repository``         : constants, helpers, file-lock primitive, and the
                             core infrastructure mixin (foundation layer)
  - ``repository_mixins``  : write / cloud-alpha / sqlite-index mixins that
                             extend the core mixin (higher layer)

``ResearchRepository`` composes the top-most sqlite mixin and is defined here.
"""

from __future__ import annotations

from brain_alpha_ops.research.repository.repository import (
    _EXPRESSION_INDEXED_FILES,
    _LOCK_POLL_SECONDS,
    _LOCK_STALE_SECONDS,
    _RECORD_INDEXED_FILES,
    _REPOSITORY_JSONL_FILES,
    _REPOSITORY_LOCK_NAMES,
    _SQLITE_INDEX_DIAGNOSTICS_FILE,
    _RepositoryFileLock,
    _cloud_alpha_id,
    _cloud_record_hash,
    _ensure_contained,
    _repository_safe,
    _with_expression_summary,
    logger,
)
from brain_alpha_ops.research.repository.repository import (
    ResearchRepositoryCoreMixin,
)
from brain_alpha_ops.research.repository.repository_mixins import (
    ResearchRepositoryCloudMixin,
    ResearchRepositorySqliteMixin,
    ResearchRepositoryWritesMixin,
)


class ResearchRepository(ResearchRepositorySqliteMixin):
    """Append-only JSONL research store with SQLite incremental indexes."""


__all__ = ["ResearchRepository"]
