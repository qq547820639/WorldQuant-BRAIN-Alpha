from __future__ import annotations

"""Internal observability helpers extracted from observability.py (Phase 2.3).

These are private implementation details used by the public API functions
in the parent module. Do not import from this module directly.
"""

"""Read-only research health and observability snapshots."""


import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_tail_with_stats
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.observability_errors import observability_error_rows
from brain_alpha_ops.research.observability_extensions import (
    load_optional_observability_sources,
    optional_observability_context,
    optional_research_health_payload,
    optional_vector_snapshot,
    sqlite_index_diagnostics,
)

SQLITE_INDEX_DIAGNOSTICS_FILE = "sqlite_index_diagnostics.jsonl"
JSONL_FILES = ("candidates.jsonl", "lifecycle.jsonl", "checks.jsonl", "backtests.jsonl", SQLITE_INDEX_DIAGNOSTICS_FILE)



def _expression_index_failure_summary(root: Path, error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "schema_version": "expression-index.v1",
        "source": "local_jsonl_expression_index",
        "storage_dir": str(root),
        "total_expression_records": 0,
        "unique_expression_count": 0,
        "duplicate_expression_count": 0,
        "source_counts": {},
        "duplicates": [],
        "frequent_expressions": [],
        "fields": [],
        "operators": [],
        "windows": [],
        "error": error,
    }


def _observability_expression_payload(summary: dict[str, Any], *, top_n: int) -> dict[str, Any]:
    total = _int_from_any(summary.get("total_expression_records"))
    unique = _int_from_any(summary.get("unique_expression_count"))
    duplicate = _int_from_any(summary.get("duplicate_expression_count"))
    duplicate_ratio = round(duplicate / unique, 4) if unique else 0.0
    return {
        "ok": summary.get("ok") is True,
        "schema_version": summary.get("schema_version", ""),
        "source": summary.get("source", ""),
        "total_expression_records": total,
        "unique_expression_count": unique,
        "duplicate_expression_count": duplicate,
        "duplicate_ratio": duplicate_ratio,
        "source_counts": summary.get("source_counts") if isinstance(summary.get("source_counts"), dict) else {},
        "top_duplicates": list(summary.get("duplicates") or [])[:top_n],
        "frequent_expressions": list(summary.get("frequent_expressions") or [])[:top_n],
        "top_fields": list(summary.get("fields") or [])[:top_n],
        "top_operators": list(summary.get("operators") or [])[:top_n],
        "top_windows": list(summary.get("windows") or [])[:top_n],
        "error": str(summary.get("error") or ""),
    }


def _check_observability(rows: list[dict[str, Any]], *, top_n: int) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    blocked_count = 0
    submittable_count = 0
    latest: list[dict[str, Any]] = []
    for row in rows:
        status = _text(row.get("status") or "unknown")
        status_counts[status] += 1
        if _truthy(row.get("submittable")):
            submittable_count += 1
        if row.get("passed") is False or row.get("submittable") is False or status.upper() == "BLOCKED":
            blocked_count += 1
        failed_rules: list[str] = []
        for check in row.get("checks") or []:
            if not isinstance(check, dict) or check.get("passed") is not False:
                continue
            name = _text(check.get("name") or "unknown")
            failure_counts[name] += 1
            failed_rules.append(name)
        latest.append(
            {
                "timestamp": row.get("checked_at") or row.get("timestamp") or "",
                "alpha_id": _text(row.get("alpha_id")),
                "status": status,
                "submittable": _truthy(row.get("submittable")),
                "failed_rules": failed_rules[:5],
            }
        )
    total = len(rows)
    cloud_self_correlation_failed = failure_counts.get("cloud_self_correlation", 0)
    return {
        "ok": True,
        "schema_version": "research_check_observability.v1",
        "total": total,
        "blocked_count": blocked_count,
        "submittable_count": submittable_count,
        "cloud_self_correlation_failed_count": cloud_self_correlation_failed,
        "cloud_self_correlation_block_rate": round(cloud_self_correlation_failed / total, 4) if total else 0.0,
        "status_counts": dict(status_counts.most_common()),
        "failed_rule_counts": dict(failure_counts.most_common()),
        "top_failed_rules": _counter_rows(failure_counts, "rule", top_n),
        "latest": latest[-top_n:][::-1],
    }


def _backtest_observability(rows: list[dict[str, Any]], *, top_n: int) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    retryable_count = 0
    failed_count = 0
    submitted_count = 0
    completed_count = 0
    scores: list[float] = []
    latest: list[dict[str, Any]] = []
    for row in rows:
        status = _normalized_status(row)
        action = _text(row.get("action") or row.get("stage") or "unknown")
        status_counts[status] += 1
        action_counts[action] += 1
        if row.get("family"):
            family_counts[_text(row.get("family"))] += 1
        if _is_backtest_failure(row):
            failed_count += 1
            failure_counts[_failure_reason(row)] += 1
        if _is_backtest_submitted(row):
            submitted_count += 1
        if _is_backtest_completed(row):
            completed_count += 1
        if _row_retryable(row):
            retryable_count += 1
        score = _float_from_any(row.get("score"))
        if score:
            scores.append(score)
        latest.append(_compact_backtest_row(row))
    total = len(rows)
    return {
        "total": total,
        "submitted_count": submitted_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "retryable_count": retryable_count,
        "failure_rate": round(failed_count / total, 4) if total else 0.0,
        "completion_rate": round(completed_count / total, 4) if total else 0.0,
        "avg_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "status_counts": dict(status_counts.most_common()),
        "action_counts": dict(action_counts.most_common(top_n)),
        "failure_patterns": _counter_rows(failure_counts, "reason", top_n),
        "families": _counter_rows(family_counts, "family", top_n),
        "latest": latest[-top_n:][::-1],
    }


def _error_observability(rows: list[dict[str, Any]], *, top_n: int) -> dict[str, Any]:
    category_counts: Counter[str] = Counter()
    code_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    retryable_count = 0
    latest: list[dict[str, Any]] = []
    for row in rows:
        category = _text(row.get("error_category") or "internal")
        code = _text(row.get("error_code") or "ERROR")
        error_type = _text(row.get("error_type") or "")
        source = _text(row.get("source") or "unknown")
        category_counts[category] += 1
        code_counts[code] += 1
        source_counts[source] += 1
        if error_type:
            type_counts[error_type] += 1
        if _truthy(row.get("retryable")):
            retryable_count += 1
        latest.append({
            "source": source,
            "timestamp": _text(row.get("timestamp") or row.get("updated_at") or row.get("checked_at")),
            "alpha_id": _text(row.get("alpha_id")),
            "error_code": code,
            "error_category": category,
            "error_type": error_type,
            "retryable": _truthy(row.get("retryable")),
            "message": redact_text(row.get("error") or row.get("message") or row.get("note") or "", max_length=180),
        })
    total = len(rows)
    return {
        "total": total,
        "retryable_count": retryable_count,
        "retryable_rate": round(retryable_count / total, 4) if total else 0.0,
        "category_counts": dict(category_counts.most_common()),
        "code_counts": dict(code_counts.most_common(top_n)),
        "type_counts": dict(type_counts.most_common(top_n)),
        "source_counts": dict(source_counts.most_common()),
        "latest": latest[-top_n:][::-1],
    }


def _expression_sqlite_status(path: Path) -> dict[str, Any]:
    exists = path.is_file()
    loaded_at, age_seconds = _path_modified_at(path if exists else None)
    row_count = 0
    error = ""
    if exists:
        try:
            with sqlite3.connect(path) as conn:
                row_count = int(conn.execute("SELECT COUNT(*) FROM expression_records").fetchone()[0])
        except sqlite3.Error as exc:
            error = redact_text(exc, max_length=180)
    return {
        "exists": exists,
        "path": str(path),
        "loaded_at": loaded_at,
        "age_seconds": age_seconds,
        "row_count": row_count,
        "error": error,
    }


def _observability_recommendations(
    expression: dict[str, Any],
    backtest_rows: list[dict[str, Any]],
    error_rows: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    expr = _observability_expression_payload(expression, top_n=3)
    if expr["duplicate_expression_count"] > 0:
        recommendations.append("Review duplicate expression fingerprints before submitting new official simulations.")
    backtests = _backtest_observability(backtest_rows, top_n=3)
    if backtests["failure_rate"] >= 0.25 and backtests["total"] >= 4:
        recommendations.append("Backtest failures are elevated; inspect failure patterns and tighten pre-submit gates.")
    errors = _error_observability(error_rows, top_n=3)
    if errors["retryable_count"]:
        recommendations.append("Retryable official/API errors are present; keep rate-limit backoff and resume queues visible.")
    if not recommendations:
        recommendations.append("No urgent observability alerts in the recent local history window.")
    return recommendations


def _counter_rows(counter: Counter[str], key: str, limit: int) -> list[dict[str, Any]]:
    return [{key: name, "count": count} for name, count in counter.most_common(limit)]


def _compact_backtest_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": row.get("timestamp", ""),
        "action": row.get("action", ""),
        "slot": row.get("slot", 0),
        "alpha_id": row.get("alpha_id", ""),
        "official_alpha_id": row.get("official_alpha_id", ""),
        "simulation_id": row.get("simulation_id", ""),
        "status": row.get("status", ""),
        "lifecycle_status": row.get("lifecycle_status", ""),
        "family": row.get("family", ""),
        "score": row.get("score", 0.0),
        "retryable": _row_retryable(row),
        "note": redact_text(row.get("note", ""), max_length=180),
    }


def _row_retryable(row: dict[str, Any]) -> bool:
    if _truthy(row.get("retryable")):
        return True
    context = row.get("error_context") if isinstance(row.get("error_context"), dict) else {}
    if _truthy(context.get("retryable")):
        return True
    text = f"{row.get('status', '')} {row.get('lifecycle_status', '')} {row.get('note', '')} {row.get('error', '')}".lower()
    return any(token in text for token in ("rate_limit", "concurrency", "retry", "timeout", "temporarily unavailable"))


def _failure_reason(row: dict[str, Any]) -> str:
    for key in ("error_code", "failure_reason", "status", "lifecycle_status", "action"):
        value = _text(row.get(key))
        if value:
            return value
    note = _text(row.get("note"))
    return note[:80] if note else "unknown_failure"


def _is_backtest_failure(row: dict[str, Any]) -> bool:
    text = f"{row.get('action', '')} {row.get('status', '')} {row.get('lifecycle_status', '')} {row.get('note', '')}".lower()
    return any(token in text for token in ("fail", "reject", "error", "blocked", "timeout"))


def _is_backtest_submitted(row: dict[str, Any]) -> bool:
    text = f"{row.get('action', '')} {row.get('status', '')} {row.get('lifecycle_status', '')}".lower()
    return any(token in text for token in ("submit", "submitted", "running", "poll"))


def _is_backtest_completed(row: dict[str, Any]) -> bool:
    text = f"{row.get('status', '')} {row.get('lifecycle_status', '')}".lower()
    if _is_backtest_failure(row):
        return True
    return any(token in text for token in ("ready", "pass", "simulated", "completed", "submitted"))


def _normalized_status(row: dict[str, Any]) -> str:
    status = _text(row.get("status") or row.get("lifecycle_status") or "unknown").lower()
    return status or "unknown"


def _looks_failed_status(text: str) -> bool:
    return any(token in text.lower() for token in ("fail", "reject", "error", "blocked", "timeout"))


def _path_modified_at(path: Path | None) -> tuple[str, int | None]:
    if not path:
        return "", None
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        return "", None
    return datetime.fromtimestamp(modified_at, timezone.utc).isoformat(), max(0, int(time.time() - modified_at))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int_from_any(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float_from_any(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique_text_items(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    seen: set[str] = set()
    rows: list[str] = []
    for item in values:
        text = _text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(text)
    return rows
