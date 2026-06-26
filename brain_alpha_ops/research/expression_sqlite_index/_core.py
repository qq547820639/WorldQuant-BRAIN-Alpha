"""SQLite cache core class for expression history.

Re-exported via ``brain_alpha_ops.research.expression_sqlite_index``.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    expression_profile_summary,
    expression_similarity,
)
from brain_alpha_ops.research.expression_index import (
    DEFAULT_SOURCES,
    ExpressionHistoryIndex,
)
from brain_alpha_ops.research.sqlite_index_manifest import build_sqlite_index_manifest

from brain_alpha_ops.research.expression_sqlite_index._helpers import (
    DEFAULT_LOOKUP_SCAN_LIMIT,
    SCHEMA_VERSION,
    _compact_record,
    _ensure_schema,
    _expression_from_record,
    _float,
    _int,
    _nested,
    _next_record_index,
    _row_to_record,
    _score_for,
    _status_for,
    _summary_from_record,
    _summary_from_records,
    _text,
)


class ExpressionSqliteIndex:
    """Optional SQLite cache over the JSONL expression history.

    JSONL remains the source of truth. This class rebuilds a compact query
    cache from the existing ExpressionHistoryIndex contract.
    """

    def __init__(self, storage_dir: str | Path = "data", db_path: str | Path | None = None):
        self.storage_dir = Path(storage_dir)
        self.db_path = Path(db_path) if db_path is not None else self.storage_dir / "expression_index.sqlite"

    def refresh(self, *, limit: int = 5000, include_cloud: bool = True) -> dict[str, Any]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        rows = ExpressionHistoryIndex(self.storage_dir).records(limit=limit, include_cloud=include_cloud)
        with closing(self._connect()) as conn:
            _ensure_schema(conn)
            conn.execute("DELETE FROM expression_records")
            # P3-3: batch commits keep WAL from growing unbounded when the
            # history has thousands of rows.  500 rows/commit balances commit
            # overhead vs. memory.
            batch_size = 500
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                conn.executemany(
                    """
                    INSERT INTO expression_records (
                        source, source_file, record_index, alpha_id, official_alpha_id,
                        simulation_id, stage, status, family, score, timestamp,
                        expression, expression_canonical, expression_fingerprint,
                        operators_json, fields_json, windows_json, profile_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            _text(row.get("source")),
                            _text(row.get("source_file")),
                            _int(row.get("record_index")),
                            _text(row.get("alpha_id")),
                            _text(row.get("official_alpha_id")),
                            _text(row.get("simulation_id")),
                            _text(row.get("stage")),
                            _text(row.get("status")),
                            _text(row.get("family")),
                            _float(row.get("score")),
                            _text(row.get("timestamp")),
                            _text(row.get("expression")),
                            _text(row.get("expression_canonical")),
                            _text(row.get("expression_fingerprint")),
                            json.dumps(
                                (row.get("expression_profile") or {}).get("operators") or [],
                                ensure_ascii=False,
                            )
                            if isinstance(row.get("expression_profile"), dict)
                            else "[]",
                            json.dumps(
                                (row.get("expression_profile") or {}).get("fields") or [],
                                ensure_ascii=False,
                            )
                            if isinstance(row.get("expression_profile"), dict)
                            else "[]",
                            json.dumps(
                                (row.get("expression_profile") or {}).get("windows") or [],
                                ensure_ascii=False,
                            )
                            if isinstance(row.get("expression_profile"), dict)
                            else "[]",
                            json.dumps(row.get("expression_profile") or {}, ensure_ascii=False, default=str)
                            if isinstance(row.get("expression_profile"), dict)
                            else "{}",
                        )
                        for row in batch
                    ),
                )
                conn.commit()
            conn.execute(
                "REPLACE INTO index_meta (key, value) VALUES (?, ?)",
                ("last_refresh", json.dumps({"limit": limit, "include_cloud": include_cloud, "record_count": len(rows)})),
            )
            conn.commit()
        return {
            "ok": True,
            "schema_version": SCHEMA_VERSION,
            "source": "sqlite_expression_index",
            "storage_dir": str(self.storage_dir),
            "db_path": str(self.db_path),
            "record_count": len(rows),
            "limit": limit,
            "include_cloud": include_cloud,
        }

    def append_record(
        self,
        record: dict[str, Any],
        *,
        source_file: str,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Incrementally index one JSONL record after it is appended.

        JSONL remains authoritative.  This method is deliberately best-effort:
        callers may ignore failures and continue writing append-only history.
        """
        if not isinstance(record, dict):
            return {
                "ok": True,
                "schema_version": SCHEMA_VERSION,
                "source": "sqlite_expression_index",
                "indexed": False,
                "reason": "record_not_mapping",
            }
        expression = _expression_from_record(record)
        if not expression:
            return {
                "ok": True,
                "schema_version": SCHEMA_VERSION,
                "source": "sqlite_expression_index",
                "indexed": False,
                "reason": "record_has_no_expression",
            }
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        source_name = source or DEFAULT_SOURCES.get(source_file, Path(source_file).stem)
        profile_summary = _summary_from_record(record, expression)
        profile = profile_summary.get("expression_profile") if isinstance(profile_summary.get("expression_profile"), dict) else {}
        with closing(self._connect()) as conn:
            with conn:
                _ensure_schema(conn)
                record_index = _next_record_index(conn, source_file)
                conn.execute(
                    """
                    INSERT INTO expression_records (
                        source, source_file, record_index, alpha_id, official_alpha_id,
                        simulation_id, stage, status, family, score, timestamp,
                        expression, expression_canonical, expression_fingerprint,
                        operators_json, fields_json, windows_json, profile_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _text(source_name),
                        _text(source_file),
                        record_index,
                        _text(record.get("alpha_id") or record.get("id") or _nested(record, "candidate", "alpha_id")),
                        _text(record.get("official_alpha_id") or _nested(record, "candidate", "official_alpha_id")),
                        _text(record.get("simulation_id") or _nested(record, "candidate", "simulation_id")),
                        _text(record.get("stage")),
                        _status_for(record),
                        _text(record.get("family") or _nested(record, "candidate", "family")),
                        _score_for(record),
                        _text(record.get("timestamp") or record.get("created_at") or record.get("synced_at")),
                        expression,
                        _text(profile_summary.get("expression_canonical")),
                        _text(profile_summary.get("expression_fingerprint")),
                        json.dumps(profile.get("operators") or [], ensure_ascii=False),
                        json.dumps(profile.get("fields") or [], ensure_ascii=False),
                        json.dumps(profile.get("windows") or [], ensure_ascii=False),
                        json.dumps(profile, ensure_ascii=False, default=str),
                    ),
                )
                conn.execute(
                    "REPLACE INTO index_meta (key, value) VALUES (?, ?)",
                    (
                        "last_incremental_append",
                        json.dumps(
                            {
                                "source_file": source_file,
                                "source": source_name,
                                "record_index": record_index,
                                "expression_fingerprint": profile_summary.get("expression_fingerprint", ""),
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                    ),
                )
        return {
            "ok": True,
            "schema_version": SCHEMA_VERSION,
            "source": "sqlite_expression_index",
            "indexed": True,
            "source_file": source_file,
            "record_index": record_index,
            "expression_fingerprint": profile_summary.get("expression_fingerprint", ""),
        }

    def summary(self, *, top_n: int = 10) -> dict[str, Any]:
        if not self.db_path.is_file():
            return {
                "ok": False,
                "schema_version": SCHEMA_VERSION,
                "source": "sqlite_expression_index",
                "db_path": str(self.db_path),
                "error_code": "INDEX_NOT_BUILT",
                "error": "SQLite expression index has not been refreshed",
            }
        with closing(self._connect()) as conn:
            _ensure_schema(conn)
            records = [_row_to_record(row) for row in conn.execute("SELECT * FROM expression_records ORDER BY id")]
            indexed_counts = {
                row["source_file"]: int(row["count"])
                for row in conn.execute("SELECT source_file, COUNT(*) AS count FROM expression_records GROUP BY source_file").fetchall()
            }
        summary = _summary_from_records(records, self.storage_dir, self.db_path, top_n=top_n)
        manifest = build_sqlite_index_manifest(
            storage_dir=self.storage_dir,
            db_path=self.db_path,
            source_files=DEFAULT_SOURCES.keys(),
            indexed_counts=indexed_counts,
        )
        summary["manifest"] = manifest
        summary["is_stale"] = manifest["is_stale"]
        return summary

    def lookup(
        self,
        expression: str,
        *,
        top_n: int = 10,
        min_similarity: float = 0.75,
        max_scan_rows: int = DEFAULT_LOOKUP_SCAN_LIMIT,
    ) -> dict[str, Any]:
        if not self.db_path.is_file():
            return {
                "ok": False,
                "schema_version": "expression-sqlite-index.lookup.v1",
                "source": "sqlite_expression_index",
                "db_path": str(self.db_path),
                "error_code": "INDEX_NOT_BUILT",
                "error": "SQLite expression index has not been refreshed",
            }
        target = expression_profile_summary(expression)
        fingerprint = str(target.get("expression_fingerprint") or "")
        with closing(self._connect()) as conn:
            _ensure_schema(conn)
            exact = [
                _compact_record(_row_to_record(row))
                for row in conn.execute(
                    "SELECT * FROM expression_records WHERE expression_fingerprint = ? ORDER BY id DESC",
                    (fingerprint,),
                )
            ]
            similar: list[dict[str, Any]] = []
            scanned_rows = 0
            scan_truncated = False
            if not exact:
                safe_scan_limit = max(1, int(max_scan_rows or DEFAULT_LOOKUP_SCAN_LIMIT))
                cursor = conn.execute(
                    "SELECT * FROM expression_records ORDER BY id DESC LIMIT ?",
                    (safe_scan_limit + 1,),
                )
                for raw_row in cursor:
                    if scanned_rows >= safe_scan_limit:
                        scan_truncated = True
                        break
                    scanned_rows += 1
                    row = _row_to_record(raw_row)
                    score = expression_similarity(
                        str(target.get("expression_canonical") or expression),
                        str(row.get("expression_canonical") or row.get("expression") or ""),
                    )
                    if score >= min_similarity:
                        similar.append({**_compact_record(row), "similarity": score})
                similar.sort(key=lambda item: item.get("similarity", 0.0), reverse=True)
        return {
            "ok": True,
            "schema_version": "expression-sqlite-index.lookup.v1",
            "source": "sqlite_expression_index",
            "expression": expression,
            **target,
            "exact_match": bool(exact),
            "exact_count": len(exact),
            "exact_records": exact[:top_n],
            "similar_count": len(similar),
            "similar_records": similar[:top_n],
            "min_similarity": min_similarity,
            "similar_scan_limit": max(1, int(max_scan_rows or DEFAULT_LOOKUP_SCAN_LIMIT)),
            "similar_scan_count": scanned_rows,
            "similar_scan_truncated": scan_truncated,
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
