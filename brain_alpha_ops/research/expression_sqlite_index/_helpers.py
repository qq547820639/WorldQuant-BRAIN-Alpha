"""SQLite cache helper functions for expression history.

Re-exported via ``brain_alpha_ops.research.expression_sqlite_index``.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    expression_profile_summary,
)

SCHEMA_VERSION = "expression-sqlite-index.v1"
DEFAULT_LOOKUP_SCAN_LIMIT = 2000


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    # P3-3: 5-second busy timeout prevents ``database is locked`` errors
    # when concurrent threads (web console + pipeline) hit the same DB.
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")  # WAL-safe, faster than FULL
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
