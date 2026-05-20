"""SQLite cache for expression history derived from append-only JSONL files."""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Any

from brain_alpha_ops.research.expression_ast import expression_profile_summary, expression_similarity
from brain_alpha_ops.research.expression_index import DEFAULT_SOURCES, ExpressionHistoryIndex
from brain_alpha_ops.research.sqlite_index_manifest import build_sqlite_index_manifest


SCHEMA_VERSION = "expression-sqlite-index.v1"


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
            with conn:
                _ensure_schema(conn)
                conn.execute("DELETE FROM expression_records")
                for row in rows:
                    profile = row.get("expression_profile") if isinstance(row.get("expression_profile"), dict) else {}
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
                            json.dumps(profile.get("operators") or [], ensure_ascii=False),
                            json.dumps(profile.get("fields") or [], ensure_ascii=False),
                            json.dumps(profile.get("windows") or [], ensure_ascii=False),
                            json.dumps(profile, ensure_ascii=False, default=str),
                        ),
                    )
                conn.execute(
                    "REPLACE INTO index_meta (key, value) VALUES (?, ?)",
                    ("last_refresh", json.dumps({"limit": limit, "include_cloud": include_cloud, "record_count": len(rows)})),
                )
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

    def lookup(self, expression: str, *, top_n: int = 10, min_similarity: float = 0.75) -> dict[str, Any]:
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
            if not exact:
                rows = [_row_to_record(row) for row in conn.execute("SELECT * FROM expression_records ORDER BY id DESC")]
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
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expression_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_file TEXT NOT NULL,
            record_index INTEGER NOT NULL,
            alpha_id TEXT,
            official_alpha_id TEXT,
            simulation_id TEXT,
            stage TEXT,
            status TEXT,
            family TEXT,
            score REAL NOT NULL DEFAULT 0,
            timestamp TEXT,
            expression TEXT NOT NULL,
            expression_canonical TEXT NOT NULL,
            expression_fingerprint TEXT NOT NULL,
            operators_json TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            windows_json TEXT NOT NULL,
            profile_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expression_fingerprint ON expression_records(expression_fingerprint)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expression_source ON expression_records(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expression_timestamp ON expression_records(timestamp)")
    conn.execute("CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def _next_record_index(conn: sqlite3.Connection, source_file: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(record_index), -1) + 1 AS next_index FROM expression_records WHERE source_file = ?",
        (source_file,),
    ).fetchone()
    try:
        return int(row["next_index"])
    except (TypeError, ValueError, KeyError):
        return 0


def _summary_from_records(records: list[dict[str, Any]], storage_dir: Path, db_path: Path, *, top_n: int) -> dict[str, Any]:
    by_fp: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, int] = {}
    field_counts: dict[str, set[str]] = {}
    operator_counts: dict[str, set[str]] = {}
    window_counts: dict[int, set[str]] = {}
    for row in records:
        fingerprint = str(row.get("expression_fingerprint") or "")
        if not fingerprint:
            continue
        source = _text(row.get("source"))
        source_counts[source] = source_counts.get(source, 0) + 1
        bucket = by_fp.setdefault(
            fingerprint,
            {
                "expression_fingerprint": fingerprint,
                "expression_canonical": row.get("expression_canonical", ""),
                "count": 0,
                "sources": {},
                "alpha_ids": [],
                "examples": [],
                "max_score": 0.0,
                "latest_timestamp": "",
                "expression_profile": row.get("expression_profile", {}),
            },
        )
        bucket["count"] += 1
        bucket["sources"][source] = bucket["sources"].get(source, 0) + 1
        if row.get("alpha_id") and row.get("alpha_id") not in bucket["alpha_ids"]:
            bucket["alpha_ids"].append(row.get("alpha_id"))
        if len(bucket["examples"]) < 3:
            bucket["examples"].append(_compact_record(row))
        bucket["max_score"] = max(float(bucket.get("max_score") or 0.0), _float(row.get("score")))
        if _text(row.get("timestamp")) >= _text(bucket.get("latest_timestamp")):
            bucket["latest_timestamp"] = _text(row.get("timestamp"))
        profile = row.get("expression_profile") if isinstance(row.get("expression_profile"), dict) else {}
        for field in profile.get("fields") or []:
            field_counts.setdefault(_text(field), set()).add(fingerprint)
        for operator in profile.get("operators") or []:
            operator_counts.setdefault(_text(operator), set()).add(fingerprint)
        for window in profile.get("windows") or []:
            try:
                window_counts.setdefault(int(float(window)), set()).add(fingerprint)
            except (TypeError, ValueError):
                continue

    duplicates = [_finalize_bucket(bucket) for bucket in by_fp.values() if int(bucket.get("count") or 0) > 1]
    duplicates.sort(key=lambda item: (item["count"], item["max_score"]), reverse=True)
    frequent = [_finalize_bucket(bucket) for bucket in by_fp.values()]
    frequent.sort(key=lambda item: (item["count"], item["max_score"], item["latest_timestamp"]), reverse=True)
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "source": "sqlite_expression_index",
        "storage_dir": str(storage_dir),
        "db_path": str(db_path),
        "total_expression_records": len(records),
        "unique_expression_count": len(by_fp),
        "duplicate_expression_count": len(duplicates),
        "source_counts": dict(sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))),
        "duplicates": duplicates[:top_n],
        "frequent_expressions": frequent[:top_n],
        "fields": _feature_rows(field_counts, "name", top_n),
        "operators": _feature_rows(operator_counts, "name", top_n),
        "windows": _window_rows(window_counts, top_n),
    }


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    profile = _loads_dict(row["profile_json"])
    return {
        "source": row["source"],
        "source_file": row["source_file"],
        "record_index": row["record_index"],
        "alpha_id": row["alpha_id"] or "",
        "official_alpha_id": row["official_alpha_id"] or "",
        "simulation_id": row["simulation_id"] or "",
        "stage": row["stage"] or "",
        "status": row["status"] or "",
        "family": row["family"] or "",
        "score": row["score"] or 0.0,
        "timestamp": row["timestamp"] or "",
        "expression": row["expression"],
        "expression_canonical": row["expression_canonical"],
        "expression_fingerprint": row["expression_fingerprint"],
        "expression_profile": profile,
    }


def _compact_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": row.get("source", ""),
        "alpha_id": row.get("alpha_id", ""),
        "official_alpha_id": row.get("official_alpha_id", ""),
        "simulation_id": row.get("simulation_id", ""),
        "stage": row.get("stage", ""),
        "status": row.get("status", ""),
        "family": row.get("family", ""),
        "score": row.get("score", 0.0),
        "timestamp": row.get("timestamp", ""),
        "expression": row.get("expression", ""),
        "expression_canonical": row.get("expression_canonical", ""),
        "expression_fingerprint": row.get("expression_fingerprint", ""),
    }


def _expression_from_record(record: dict[str, Any]) -> str:
    expression = record.get("expression")
    if isinstance(expression, dict):
        code = expression.get("code") or expression.get("regular")
        if code:
            return _text(code)
    if expression:
        return _text(expression)

    candidate = record.get("candidate")
    if isinstance(candidate, dict):
        nested = _expression_from_record(candidate)
        if nested:
            return nested

    regular = record.get("regular")
    if isinstance(regular, dict) and regular.get("code"):
        return _text(regular.get("code"))

    raw = record.get("raw")
    if isinstance(raw, dict):
        raw_regular = raw.get("regular")
        if isinstance(raw_regular, dict) and raw_regular.get("code"):
            return _text(raw_regular.get("code"))

    return _text(record.get("expression_canonical"))


def _summary_from_record(record: dict[str, Any], expression: str) -> dict[str, Any]:
    fingerprint = _text(record.get("expression_fingerprint"))
    canonical = _text(record.get("expression_canonical"))
    profile = record.get("expression_profile") if isinstance(record.get("expression_profile"), dict) else {}
    if fingerprint and canonical and profile:
        return {
            "expression_canonical": canonical,
            "expression_fingerprint": fingerprint,
            "expression_profile": profile,
        }
    return expression_profile_summary(expression)


def _status_for(record: dict[str, Any]) -> str:
    metrics = record.get("official_metrics") if isinstance(record.get("official_metrics"), dict) else {}
    nested_metrics = _nested(record, "candidate", "official_metrics")
    if not isinstance(nested_metrics, dict):
        nested_metrics = {}
    return _text(
        record.get("lifecycle_status")
        or record.get("status")
        or metrics.get("pass_fail")
        or nested_metrics.get("pass_fail")
    )


def _score_for(record: dict[str, Any]) -> float:
    scorecard = record.get("scorecard") if isinstance(record.get("scorecard"), dict) else {}
    nested_scorecard = _nested(record, "candidate", "scorecard")
    if isinstance(nested_scorecard, dict) and not scorecard:
        scorecard = nested_scorecard
    return _float(scorecard.get("total_score", record.get("score", 0.0)))


def _nested(record: dict[str, Any], *keys: str) -> Any:
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return value


def _finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        "expression_fingerprint": bucket.get("expression_fingerprint", ""),
        "expression_canonical": bucket.get("expression_canonical", ""),
        "count": int(bucket.get("count") or 0),
        "source_count": len(bucket.get("sources") or {}),
        "sources": dict(sorted((bucket.get("sources") or {}).items(), key=lambda item: (-item[1], item[0]))),
        "alpha_ids": list(bucket.get("alpha_ids") or [])[:10],
        "max_score": round(float(bucket.get("max_score") or 0.0), 3),
        "latest_timestamp": _text(bucket.get("latest_timestamp")),
        "expression_profile": bucket.get("expression_profile", {}),
        "examples": list(bucket.get("examples") or []),
    }


def _feature_rows(values: dict[str, set[str]], key_name: str, top_n: int) -> list[dict[str, Any]]:
    rows = [
        {key_name: name, "unique_expression_count": len(fingerprints)}
        for name, fingerprints in values.items()
        if name
    ]
    rows.sort(key=lambda item: (-item["unique_expression_count"], item[key_name]))
    return rows[:top_n]


def _window_rows(values: dict[int, set[str]], top_n: int) -> list[dict[str, Any]]:
    rows = [
        {"window": window, "unique_expression_count": len(fingerprints)}
        for window, fingerprints in values.items()
    ]
    rows.sort(key=lambda item: (-item["unique_expression_count"], item["window"]))
    return rows[:top_n]


def _loads_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
