"""Cloud-Alpha merge/read mixin for ``ResearchRepository``."""

from __future__ import annotations

import json
from typing import Any

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.repository._constants import (
    _cloud_alpha_id,
    _cloud_record_hash,
    _repository_safe,
    logger,
)
from brain_alpha_ops.research.repository._writes_mixin import ResearchRepositoryWritesMixin


class ResearchRepositoryCloudMixin(ResearchRepositoryWritesMixin):
    def cloud_alpha_ids(self) -> set[str]:
        return set(self._latest_cloud_alpha_rows().keys())

    def latest_cloud_alphas(self) -> list[dict[str, Any]]:
        return list(self._latest_cloud_alpha_rows().values())

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
        path = self._safe_storage_path("cloud_alphas.jsonl")
        latest: dict[str, dict[str, Any]] = {}
        if not path.exists():
            return latest
        try:
            with path.open("r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, start=1):
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "corrupt cloud alpha JSON line skipped: %s:%d: %s",
                            redact_text(str(path), max_length=180),
                            line_number,
                            redact_error_message(exc),
                        )
                        continue
                    alpha_id = _cloud_alpha_id(record)
                    if alpha_id:
                        latest[alpha_id] = record
        except OSError:
            return latest
        return latest
