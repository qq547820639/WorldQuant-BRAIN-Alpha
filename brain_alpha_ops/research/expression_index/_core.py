"""Expression history index built from append-only research JSONL files.

Re-exported via ``brain_alpha_ops.research.expression_index``.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    expression_profile_summary,
    expression_similarity,
)

from brain_alpha_ops.research.expression_index._buckets import (
    _compat_lookup_schema,
    _compat_summary_schema,
    _expression_bucket,
    _feature_bucket,
    _finalize_expression_bucket,
    _rank_feature_buckets,
    _rank_window_buckets,
    _update_expression_bucket,
    _update_feature_bucket,
)
from brain_alpha_ops.research.expression_index._helpers import (
    _as_int_list,
    _as_text_list,
    _compact_record,
    _nested,
    _score_for,
    _status_for,
    _text,
)
from brain_alpha_ops.research.expression_index._records import (
    _expression_from_record,
    _source_records_for,
    _summary_from_record,
)

logger = logging.getLogger("brain_alpha_ops.research.expression_index")


DEFAULT_SOURCES = {
    "candidates.jsonl": "candidate",
    "lifecycle.jsonl": "lifecycle",
    "checks.jsonl": "check",
    "backtests.jsonl": "backtest",
    "submissions.jsonl": "submission",
    "cloud_alphas.jsonl": "cloud_alpha",
}


class ExpressionHistoryIndex:
    def __init__(self, storage_dir: str | Path = "data"):
        self.storage_dir = Path(storage_dir)

    def summary(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_cloud: bool = True,
        source_rows: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        if source_rows is None:
            sqlite_summary = self._sqlite_summary(top_n=top_n)
            if sqlite_summary.get("ok"):
                return _compat_summary_schema(sqlite_summary)
        rows = self.records(limit=limit, include_cloud=include_cloud, source_rows=source_rows)
        buckets: dict[str, dict[str, Any]] = {}
        field_buckets: dict[str, dict[str, Any]] = defaultdict(_feature_bucket)
        operator_buckets: dict[str, dict[str, Any]] = defaultdict(_feature_bucket)
        window_buckets: dict[int, dict[str, Any]] = defaultdict(_feature_bucket)
        source_counts: Counter[str] = Counter()

        for row in rows:
            fingerprint = str(row.get("expression_fingerprint") or "")
            if not fingerprint:
                continue
            source = str(row.get("source") or "")
            source_counts[source] += 1
            bucket = buckets.setdefault(fingerprint, _expression_bucket(row))
            _update_expression_bucket(bucket, row)
            profile = row.get("expression_profile") if isinstance(row.get("expression_profile"), dict) else {}
            for field in _as_text_list(profile.get("fields")):
                _update_feature_bucket(field_buckets[field], fingerprint, source)
            for operator in _as_text_list(profile.get("operators")):
                _update_feature_bucket(operator_buckets[operator], fingerprint, source)
            for window in _as_int_list(profile.get("windows")):
                _update_feature_bucket(window_buckets[window], fingerprint, source)

        duplicate_rows = [
            _finalize_expression_bucket(bucket)
            for bucket in buckets.values()
            if int(bucket.get("count") or 0) > 1
        ]
        duplicate_rows.sort(key=lambda item: (item["count"], item["source_count"], item["max_score"]), reverse=True)

        frequent_rows = [_finalize_expression_bucket(bucket) for bucket in buckets.values()]
        frequent_rows.sort(key=lambda item: (item["count"], item["max_score"], item["latest_timestamp"]), reverse=True)

        return {
            "ok": True,
            "schema_version": "expression-index.v1",
            "source": "local_jsonl_expression_index",
            "storage_dir": str(self.storage_dir),
            "total_expression_records": len(rows),
            "unique_expression_count": len(buckets),
            "duplicate_expression_count": len(duplicate_rows),
            "source_counts": dict(source_counts.most_common()),
            "duplicates": duplicate_rows[:top_n],
            "frequent_expressions": frequent_rows[:top_n],
            "fields": _rank_feature_buckets(field_buckets, top_n),
            "operators": _rank_feature_buckets(operator_buckets, top_n),
            "windows": _rank_window_buckets(window_buckets, top_n),
        }

    def lookup(
        self,
        expression: str,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_cloud: bool = True,
        min_similarity: float = 0.75,
        max_scan_rows: int = 2000,
        source_rows: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        if source_rows is None:
            sqlite_lookup = self._sqlite_lookup(
                expression,
                top_n=top_n,
                min_similarity=min_similarity,
                max_scan_rows=max_scan_rows,
            )
            if sqlite_lookup.get("ok"):
                return _compat_lookup_schema(sqlite_lookup)
        target = expression_profile_summary(expression)
        target_fingerprint = str(target.get("expression_fingerprint") or "")
        rows = self.records(limit=limit, include_cloud=include_cloud, source_rows=source_rows)
        exact = [
            _compact_record(row)
            for row in rows
            if str(row.get("expression_fingerprint") or "") == target_fingerprint
        ]
        similar: list[dict[str, Any]] = []
        if not exact:
            for row in rows:
                score = expression_similarity(
                    str(target.get("expression_canonical") or expression),
                    str(row.get("expression_canonical") or row.get("expression") or ""),
                )
                if score >= min_similarity:
                    similar.append({**_compact_record(row), "similarity": score})
            similar.sort(key=lambda item: item.get("similarity", 0.0), reverse=True)
        return {
            "ok": True,
            "schema_version": "expression-index.lookup.v1",
            "expression": expression,
            **target,
            "exact_match": bool(exact),
            "exact_count": len(exact),
            "exact_records": exact[:top_n],
            "similar_count": len(similar),
            "similar_records": similar[:top_n],
            "min_similarity": min_similarity,
        }

    def _sqlite_summary(self, *, top_n: int) -> dict[str, Any]:
        db_path = self.storage_dir / "expression_index.sqlite"
        if not db_path.is_file():
            return {}
        try:
            from brain_alpha_ops.research.expression_sqlite_index import (
                ExpressionSqliteIndex,
            )

            return ExpressionSqliteIndex(self.storage_dir).summary(top_n=top_n)
        except Exception as exc:
            logger.warning("sqlite expression index summary unavailable", exc_info=True)
            return {}

    def _sqlite_lookup(self, expression: str, *, top_n: int, min_similarity: float, max_scan_rows: int) -> dict[str, Any]:
        db_path = self.storage_dir / "expression_index.sqlite"
        if not db_path.is_file():
            return {}
        try:
            from brain_alpha_ops.research.expression_sqlite_index import (
                ExpressionSqliteIndex,
            )

            return ExpressionSqliteIndex(self.storage_dir).lookup(
                expression,
                top_n=top_n,
                min_similarity=min_similarity,
                max_scan_rows=max_scan_rows,
            )
        except Exception as exc:
            logger.warning("sqlite expression index lookup unavailable", exc_info=True)
            return {}

    def records(
        self,
        *,
        limit: int = 5000,
        include_cloud: bool = True,
        source_rows: dict[str, list[dict[str, Any]]] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        sources = dict(DEFAULT_SOURCES)
        if not include_cloud:
            sources.pop("cloud_alphas.jsonl", None)
        for filename, source in sources.items():
            records = _source_records_for(filename, source_rows, self.storage_dir, limit=limit)
            for index, record in enumerate(records):
                expression = _expression_from_record(record)
                if not expression:
                    continue
                summary = _summary_from_record(record, expression)
                rows.append({
                    "source": source,
                    "source_file": filename,
                    "record_index": index,
                    "alpha_id": _text(record.get("alpha_id") or record.get("id") or _nested(record, "candidate", "alpha_id")),
                    "official_alpha_id": _text(record.get("official_alpha_id") or _nested(record, "candidate", "official_alpha_id")),
                    "simulation_id": _text(record.get("simulation_id") or _nested(record, "candidate", "simulation_id")),
                    "stage": _text(record.get("stage")),
                    "status": _status_for(record),
                    "family": _text(record.get("family") or _nested(record, "candidate", "family")),
                    "score": _score_for(record),
                    "timestamp": _text(record.get("timestamp") or record.get("created_at") or record.get("synced_at")),
                    "expression": expression,
                    **summary,
                })
        return rows[-max(1, int(limit or 1)):]
