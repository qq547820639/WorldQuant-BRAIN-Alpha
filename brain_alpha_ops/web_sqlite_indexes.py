"""Read-only SQLite index snapshots for the local web API."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.research.expression_sqlite_index import ExpressionSqliteIndex
from brain_alpha_ops.research.record_sqlite_index import RecordSqliteIndex


LoadConfig = Callable[[], RunConfig]
WebError = Callable[[Exception, str], dict[str, Any]]


def _default_web_error(exc: Exception, error_code: str) -> dict[str, Any]:
    return {"ok": False, "error_code": error_code, "error": str(exc)}


def sqlite_index_snapshot(
    *,
    top_n: int = 10,
    load_config: LoadConfig = load_run_config,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        storage_dir = config.ops.storage_dir
        expression_index = ExpressionSqliteIndex(storage_dir).summary(top_n=top_n)
        record_index = RecordSqliteIndex(storage_dir).summary()
        return {
            "ok": True,
            "schema_version": "sqlite_index_snapshot.v1",
            "source": "sqlite_index_cache",
            "storage_dir": str(storage_dir),
            "expression_index": expression_index,
            "record_index": record_index,
            "has_missing_index": expression_index.get("ok") is False or record_index.get("ok") is False,
            "has_stale_index": bool(expression_index.get("is_stale") or record_index.get("is_stale")),
        }
    except Exception as exc:
        return web_error(exc, "SQLITE_INDEX_SNAPSHOT_ERROR")


def sqlite_expression_lookup_payload(
    *,
    expression: str,
    top_n: int = 10,
    min_similarity: float = 0.75,
    load_config: LoadConfig = load_run_config,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        return ExpressionSqliteIndex(config.ops.storage_dir).lookup(
            expression,
            top_n=top_n,
            min_similarity=min_similarity,
        )
    except Exception as exc:
        return web_error(exc, "SQLITE_EXPRESSION_LOOKUP_ERROR")


def sqlite_record_lookup_payload(
    *,
    alpha_id: str,
    limit: int = 50,
    load_config: LoadConfig = load_run_config,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        return RecordSqliteIndex(config.ops.storage_dir).lookup_alpha(alpha_id, limit=limit)
    except Exception as exc:
        return web_error(exc, "SQLITE_RECORD_LOOKUP_ERROR")
