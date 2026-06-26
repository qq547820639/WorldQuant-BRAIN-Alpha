"""SQLite incremental-index update mixin for ``ResearchRepository``."""

from __future__ import annotations

import json
from typing import Any

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.repository._constants import (
    _EXPRESSION_INDEXED_FILES,
    _RECORD_INDEXED_FILES,
    _SQLITE_INDEX_DIAGNOSTICS_FILE,
    _repository_safe,
    logger,
)
from brain_alpha_ops.research.repository._cloud_mixin import ResearchRepositoryCloudMixin


class ResearchRepositorySqliteMixin(ResearchRepositoryCloudMixin):
    def _update_expression_sqlite_cache(self, filename: str, record: dict[str, Any]) -> None:
        if filename not in _EXPRESSION_INDEXED_FILES:
            return
        try:
            from brain_alpha_ops.research.expression_sqlite_index import (
                ExpressionSqliteIndex,
            )

            ExpressionSqliteIndex(self.storage_dir).append_record(record, source_file=filename)
        except Exception as exc:
            message = redact_error_message(exc)
            logger.warning(
                "failed to update incremental expression sqlite cache for %s: %s",
                redact_text(filename, max_length=120),
                message,
            )
            self._record_sqlite_cache_diagnostic(
                component="expression_sqlite_index",
                source_file=filename,
                error=message,
            )

    def _update_record_sqlite_cache(self, filename: str, record: dict[str, Any]) -> None:
        if filename not in _RECORD_INDEXED_FILES:
            return
        try:
            from brain_alpha_ops.research.record_sqlite_index import RecordSqliteIndex

            RecordSqliteIndex(self.storage_dir).append_record(record, source_file=filename)
        except Exception as exc:
            message = redact_error_message(exc)
            logger.warning(
                "failed to update incremental record sqlite cache for %s: %s",
                redact_text(filename, max_length=120),
                message,
            )
            self._record_sqlite_cache_diagnostic(
                component="record_sqlite_index",
                source_file=filename,
                error=message,
            )

    def _record_sqlite_cache_diagnostic(self, *, component: str, source_file: str, error: str) -> None:
        record = _repository_safe(
            {
                "timestamp": utc_now(),
                "source": "sqlite_index",
                "component": component,
                "source_file": source_file,
                "status": "index_update_failed",
                "error": error,
                "error_context": {
                    "error_code": "SQLITE_INDEX_UPDATE_FAILED",
                    "error": error,
                    "component": component,
                    "source_file": source_file,
                },
                "action": "Rebuild the SQLite research indexes or continue with bounded JSONL lookups.",
            }
        )
        try:
            with self._file_lock(_SQLITE_INDEX_DIAGNOSTICS_FILE):
                path = self._safe_storage_path(_SQLITE_INDEX_DIAGNOSTICS_FILE)
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:
            logger.warning(
                "failed to persist sqlite index diagnostic for %s: %s",
                redact_text(source_file, max_length=120),
                redact_error_message(exc),
            )
