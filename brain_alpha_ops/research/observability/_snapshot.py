"""Build research observability snapshots from local JSONL history."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_tail_with_stats
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.observability_errors import observability_error_rows
from brain_alpha_ops.research._observability_helpers import (
    _expression_index_failure_summary,
    _observability_expression_payload,
    _backtest_observability,
    _check_observability,
    _error_observability,
    _expression_sqlite_status,
)
from brain_alpha_ops.research.observability_extensions import (
    load_optional_observability_sources,
    optional_vector_snapshot,
    sqlite_index_diagnostics,
)
from brain_alpha_ops.research.observability._context import official_call_guard_observability
from brain_alpha_ops.research.observability._health import diagnose_research_health

SQLITE_INDEX_DIAGNOSTICS_FILE = "sqlite_index_diagnostics.jsonl"
JSONL_FILES = ("candidates.jsonl", "lifecycle.jsonl", "checks.jsonl", "backtests.jsonl", SQLITE_INDEX_DIAGNOSTICS_FILE)


def build_research_observability_snapshot(
    storage_dir: str | Path,
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_cloud: bool = True,
    job_rows: list[dict[str, Any]] | None = None,
    job_diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a local-only health snapshot from append-only research history."""
    root = Path(storage_dir)
    safe_limit = max(1, int(limit or 1))
    safe_top_n = max(1, int(top_n or 1))
    jsonl_results = {
        name: read_jsonl_tail_with_stats(root / name, limit=safe_limit)
        for name in JSONL_FILES
    }
    source_rows = {name: result.rows for name, result in jsonl_results.items()}
    expression_error = ""
    try:
        expression = ExpressionHistoryIndex(root).summary(
            limit=safe_limit,
            top_n=safe_top_n,
            include_cloud=include_cloud,
            source_rows=source_rows,
        )
    except Exception as exc:
        expression_error = redact_error_message(exc, max_length=240)
        expression = _expression_index_failure_summary(root, expression_error)
    backtest_rows = source_rows.get("backtests.jsonl", [])
    lifecycle_rows = source_rows.get("lifecycle.jsonl", [])
    check_rows = source_rows.get("checks.jsonl", [])
    job_diagnostic_rows = list(job_diagnostics or [])
    sqlite_diagnostic_rows = source_rows.get(SQLITE_INDEX_DIAGNOSTICS_FILE, [])
    combined_job_rows = list(job_rows or []) + job_diagnostic_rows + sqlite_diagnostic_rows
    error_rows = observability_error_rows(
        backtest_rows,
        lifecycle_rows,
        check_rows,
        combined_job_rows,
    )
    expression_payload = _observability_expression_payload(expression, top_n=safe_top_n)
    backtest_payload = _backtest_observability(backtest_rows, top_n=safe_top_n)
    check_payload = _check_observability(check_rows, top_n=safe_top_n)
    error_payload = _error_observability(error_rows, top_n=safe_top_n)
    official_call_guard = official_call_guard_observability(lifecycle_rows, top_n=safe_top_n)
    jsonl_payload = {name: result.to_dict() for name, result in jsonl_results.items()}
    sqlite_payload = _expression_sqlite_status(root / "expression_index.sqlite")
    sqlite_diagnostics_payload = sqlite_index_diagnostics(sqlite_diagnostic_rows, top_n=safe_top_n)
    market_cache_payload, alert_payload = load_optional_observability_sources(root, top_n=safe_top_n)
    market_vector_payload = optional_vector_snapshot(root, top_n=safe_top_n)
    health = diagnose_research_health(
        expression_payload=expression_payload,
        backtests=backtest_payload,
        checks=check_payload,
        errors=error_payload,
        jsonl=jsonl_payload,
        sqlite_cache=sqlite_payload,
        sqlite_index_diagnostics=sqlite_diagnostics_payload,
        market_data_cache=market_cache_payload,
        alerts=alert_payload,
    )
    partial_errors = []
    if expression_payload.get("error"):
        partial_errors.append(
            {
                "component": "expression_index",
                "error": expression_payload.get("error", ""),
            }
        )
    for row in job_diagnostic_rows:
        partial_errors.append({
            "component": "job_rows",
            "source": row.get("source", ""),
            "error": row.get("error", ""),
        })
    for row in sqlite_diagnostic_rows:
        partial_errors.append({
            "component": "sqlite_index",
            "source": row.get("source_file", ""),
            "error": row.get("error", ""),
        })
    return {
        "ok": True,
        "schema_version": "research_observability_snapshot.v1",
        "source": "local_research_jsonl",
        "storage_dir": str(root),
        "limit": safe_limit,
        "top_n": safe_top_n,
        "include_cloud": bool(include_cloud),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expression_index": expression_payload,
        "backtests": backtest_payload,
        "checks": check_payload,
        "errors": error_payload,
        "official_call_guard": official_call_guard,
        "job_diagnostics": job_diagnostic_rows,
        "jsonl": jsonl_payload,
        "sqlite_cache": sqlite_payload,
        "sqlite_index_diagnostics": sqlite_diagnostics_payload,
        "market_data_cache": market_cache_payload,
        "market_data_vector": market_vector_payload,
        "alerts": alert_payload,
        "health": health,
        "partial_errors": partial_errors,
        "recommendations": list(health.get("actions") or []),
    }
