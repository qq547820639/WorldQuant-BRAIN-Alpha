"""SQLite record index for cloud alpha and backtest audit logs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.sqlite_index_manifest import build_sqlite_index_manifest


SCHEMA_VERSION = "record-sqlite-index.v1"
SUPPORTED_SOURCES = {
    "cloud_alphas.jsonl": "cloud_alpha",
    "backtests.jsonl": "backtest_record",
}


class RecordSqliteIndex:
    """Optional SQLite cache over high-volume JSONL record streams."""

    def __init__(self, storage_dir: str | Path, db_path: str | Path | None = None):
        self.storage_dir = Path(storage_dir)
        self.db_path = Path(db_path) if db_path is not None else self.storage_dir / "records_index.sqlite"

    def append_record(self, record: dict[str, Any], *, source_file: str) -> dict[str, Any]:
        kind = SUPPORTED_SOURCES.get(str(source_file or ""))
        if not kind:
            return {"ok": False, "reason": "unsupported_source", "source_file": source_file}
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            _ensure_schema(conn)
            record_index = _next_record_index(conn, source_file)
            conn.execute(
                """
                INSERT OR REPLACE INTO records (
                    source_file, record_index, kind, record_id, alpha_id, official_alpha_id,
                    simulation_id, expression_key, status, action, timestamp, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _row_values(record, source_file=source_file, kind=kind, record_index=record_index),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "schema_version": SCHEMA_VERSION, "source_file": source_file, "record_index": record_index}

    def refresh(self, *, limit: int = 10000) -> dict[str, Any]:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            _ensure_schema(conn)
            conn.execute("DELETE FROM records")
            inserted = 0
            for source_file, kind in SUPPORTED_SOURCES.items():
                rows = read_jsonl_tail(self.storage_dir / source_file, limit=max(1, int(limit or 1)))
                for record_index, record in enumerate(rows):
                    if not isinstance(record, dict):
                        continue
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO records (
                            source_file, record_index, kind, record_id, alpha_id, official_alpha_id,
                            simulation_id, expression_key, status, action, timestamp, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        _row_values(record, source_file=source_file, kind=kind, record_index=record_index),
                    )
                    inserted += 1
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "schema_version": SCHEMA_VERSION, "record_count": inserted}

    def summary(self) -> dict[str, Any]:
        if not self.db_path.is_file():
            return {
                "ok": False,
                "schema_version": SCHEMA_VERSION,
                "error_code": "INDEX_NOT_BUILT",
                "error": "SQLite record index has not been refreshed",
            }
        conn = self._connect()
        try:
            _ensure_schema(conn)
            counts = {
                row["kind"]: int(row["count"])
                for row in conn.execute("SELECT kind, COUNT(*) AS count FROM records GROUP BY kind").fetchall()
            }
            row_count = int(conn.execute("SELECT COUNT(*) AS count FROM records").fetchone()["count"])
            latest = conn.execute("SELECT timestamp FROM records WHERE timestamp != '' ORDER BY timestamp DESC LIMIT 1").fetchone()
            indexed_counts = {
                row["source_file"]: int(row["count"])
                for row in conn.execute("SELECT source_file, COUNT(*) AS count FROM records GROUP BY source_file").fetchall()
            }
        finally:
            conn.close()
        manifest = build_sqlite_index_manifest(
            storage_dir=self.storage_dir,
            db_path=self.db_path,
            source_files=SUPPORTED_SOURCES.keys(),
            indexed_counts=indexed_counts,
        )
        return {
            "ok": True,
            "schema_version": SCHEMA_VERSION,
            "source": "sqlite_record_index",
            "db_path": str(self.db_path),
            "row_count": row_count,
            "counts": counts,
            "latest_timestamp": latest["timestamp"] if latest else "",
            "manifest": manifest,
            "is_stale": manifest["is_stale"],
        }

    def lookup_alpha(self, alpha_id: str, *, limit: int = 50) -> dict[str, Any]:
        wanted = str(alpha_id or "").strip()
        if not wanted:
            return {"ok": False, "schema_version": SCHEMA_VERSION, "error_code": "VALIDATION_ERROR", "error": "alpha_id is required"}
        if not self.db_path.is_file():
            return {"ok": False, "schema_version": SCHEMA_VERSION, "error_code": "INDEX_NOT_BUILT", "error": "SQLite record index has not been refreshed"}
        conn = self._connect()
        try:
            _ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT * FROM records
                WHERE alpha_id = ? OR official_alpha_id = ? OR simulation_id = ?
                ORDER BY source_file, record_index DESC
                LIMIT ?
                """,
                (wanted, wanted, wanted, max(1, int(limit or 1))),
            ).fetchall()
        finally:
            conn.close()
        return {
            "ok": True,
            "schema_version": SCHEMA_VERSION + ".lookup.v1",
            "source": "sqlite_record_index",
            "alpha_id": wanted,
            "count": len(rows),
            "records": [_row_to_record(row) for row in rows],
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            source_file TEXT NOT NULL,
            record_index INTEGER NOT NULL,
            kind TEXT NOT NULL,
            record_id TEXT NOT NULL,
            alpha_id TEXT NOT NULL DEFAULT '',
            official_alpha_id TEXT NOT NULL DEFAULT '',
            simulation_id TEXT NOT NULL DEFAULT '',
            expression_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL,
            PRIMARY KEY (source_file, record_index)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_alpha_id ON records(alpha_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_official_alpha_id ON records(official_alpha_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_simulation_id ON records(simulation_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_expression_key ON records(expression_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_kind_status ON records(kind, status)")


def _next_record_index(conn: sqlite3.Connection, source_file: str) -> int:
    row = conn.execute("SELECT MAX(record_index) AS max_index FROM records WHERE source_file = ?", (source_file,)).fetchone()
    value = row["max_index"] if row else None
    return 0 if value is None else int(value) + 1


def _row_values(record: dict[str, Any], *, source_file: str, kind: str, record_index: int) -> tuple[Any, ...]:
    clean = redact_data(dict(record or {}))
    expression = str(clean.get("expression") or "")
    expr_key = str(clean.get("expression_canonical") or clean.get("expression_key") or expression_key(expression))
    alpha_id = str(clean.get("alpha_id") or clean.get("id") or "")
    official_alpha_id = str(clean.get("official_alpha_id") or "")
    metrics = clean.get("metrics") if isinstance(clean.get("metrics"), dict) else {}
    if not official_alpha_id:
        official_alpha_id = str(metrics.get("official_alpha_id") or metrics.get("alpha_id") or "")
    simulation_id = str(clean.get("simulation_id") or "")
    record_id = _record_id(clean, source_file=source_file, record_index=record_index)
    return (
        source_file,
        record_index,
        kind,
        record_id,
        alpha_id,
        official_alpha_id,
        simulation_id,
        expr_key,
        str(clean.get("status") or clean.get("lifecycle_status") or ""),
        str(clean.get("action") or ""),
        str(clean.get("timestamp") or clean.get("synced_at") or ""),
        json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str),
    )


def _record_id(record: dict[str, Any], *, source_file: str, record_index: int) -> str:
    for key in ("cloud_record_hash", "record_id", "id", "alpha_id", "simulation_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{source_file}:{record_index}:{digest}"


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload_json"])
    return {
        "source_file": row["source_file"],
        "record_index": row["record_index"],
        "kind": row["kind"],
        "record_id": row["record_id"],
        "alpha_id": row["alpha_id"],
        "official_alpha_id": row["official_alpha_id"],
        "simulation_id": row["simulation_id"],
        "expression_key": row["expression_key"],
        "status": row["status"],
        "action": row["action"],
        "timestamp": row["timestamp"],
        "payload": payload,
    }
