"""Read-only research health and observability snapshots."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from typing import Any

from brain_alpha_ops.errors import classify_error
from brain_alpha_ops.jsonl import read_jsonl_tail_with_stats
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex


JSONL_FILES = ("candidates.jsonl", "lifecycle.jsonl", "checks.jsonl", "backtests.jsonl")


def build_research_observability_snapshot(
    storage_dir: str | Path,
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_cloud: bool = True,
    job_rows: list[dict[str, Any]] | None = None,
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
    error_rows = _observability_error_rows(
        backtest_rows,
        lifecycle_rows,
        check_rows,
        list(job_rows or []),
    )
    expression_payload = _observability_expression_payload(expression, top_n=safe_top_n)
    backtest_payload = _backtest_observability(backtest_rows, top_n=safe_top_n)
    error_payload = _error_observability(error_rows, top_n=safe_top_n)
    official_call_guard = official_call_guard_observability(lifecycle_rows, top_n=safe_top_n)
    jsonl_payload = {name: result.to_dict() for name, result in jsonl_results.items()}
    sqlite_payload = _expression_sqlite_status(root / "expression_index.sqlite")
    health = diagnose_research_health(
        expression_payload=expression_payload,
        backtests=backtest_payload,
        errors=error_payload,
        jsonl=jsonl_payload,
        sqlite_cache=sqlite_payload,
    )
    partial_errors = []
    if expression_payload.get("error"):
        partial_errors.append(
            {
                "component": "expression_index",
                "error": expression_payload.get("error", ""),
            }
        )
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
        "errors": error_payload,
        "official_call_guard": official_call_guard,
        "jsonl": jsonl_payload,
        "sqlite_cache": sqlite_payload,
        "health": health,
        "partial_errors": partial_errors,
        "recommendations": list(health.get("actions") or []),
    }


def observability_context(snapshot: dict[str, Any] | None, *, top_n: int = 10) -> dict[str, Any]:
    """Return a compact LLM-context view of the full observability snapshot."""
    snapshot = snapshot or {}
    expression = snapshot.get("expression_index") if isinstance(snapshot.get("expression_index"), dict) else {}
    backtests = snapshot.get("backtests") if isinstance(snapshot.get("backtests"), dict) else {}
    errors = snapshot.get("errors") if isinstance(snapshot.get("errors"), dict) else {}
    official_guard = snapshot.get("official_call_guard") if isinstance(snapshot.get("official_call_guard"), dict) else {}
    sqlite_cache = snapshot.get("sqlite_cache") if isinstance(snapshot.get("sqlite_cache"), dict) else {}
    health = snapshot.get("health") if isinstance(snapshot.get("health"), dict) else {}
    return {
        "schema_version": snapshot.get("schema_version", "research_observability_snapshot.v1"),
        "source": snapshot.get("source", "local_research_jsonl"),
        "generated_at": snapshot.get("generated_at", ""),
        "risk_level": health.get("risk_level", "unknown"),
        "health_flags": list(health.get("health_flags") or [])[:top_n],
        "blocking_flags": list(health.get("blocking_flags") or [])[:top_n],
        "warning_flags": list(health.get("warning_flags") or [])[:top_n],
        "expression_records": expression.get("total_expression_records", 0),
        "unique_expression_count": expression.get("unique_expression_count", 0),
        "duplicate_expression_count": expression.get("duplicate_expression_count", 0),
        "duplicate_ratio": expression.get("duplicate_ratio", 0.0),
        "backtest_total": backtests.get("total", 0),
        "backtest_failure_rate": backtests.get("failure_rate", 0.0),
        "backtest_retryable_count": backtests.get("retryable_count", 0),
        "error_total": errors.get("total", 0),
        "retryable_error_count": errors.get("retryable_count", 0),
        "official_guard_blocked_count": official_guard.get("blocked_count", 0),
        "official_guard_validation_blocked_count": official_guard.get("validation_blocked_count", 0),
        "official_guard_simulation_blocked_count": official_guard.get("simulation_blocked_count", 0),
        "official_guard_recent": list(official_guard.get("recent_blocks") or [])[:top_n],
        "top_error_categories": dict(errors.get("category_counts") or {}),
        "top_error_codes": dict(errors.get("code_counts") or {}),
        "top_backtest_failures": list(backtests.get("failure_patterns") or [])[:top_n],
        "sqlite_cache_ready": bool(sqlite_cache.get("exists") and not sqlite_cache.get("error")),
        "recommended_actions": list(health.get("actions") or snapshot.get("recommendations") or [])[:top_n],
        "recommendations": list(health.get("actions") or snapshot.get("recommendations") or [])[:top_n],
    }


def official_call_guard_observability(rows: list[dict[str, Any]], *, top_n: int = 10) -> dict[str, Any]:
    """Summarize persisted duplicate-expression official-call guard blocks."""
    safe_top_n = max(1, int(top_n or 1))
    phase_counts: Counter[str] = Counter()
    expression_counts: Counter[str] = Counter()
    recent_blocks: list[dict[str, Any]] = []
    for row in rows:
        stage = _text(row.get("stage"))
        status = _text(row.get("status"))
        gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
        failed_reasons = [str(item) for item in gate.get("failed_reasons") or [] if str(item)]
        blocked = (
            stage == "observability_duplicate_blocked"
            or status == "observability_duplicate_blocked"
            or gate.get("status") == "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED"
            or any("observability duplicate expression history blocked official call" in item for item in failed_reasons)
        )
        if not blocked:
            continue
        phase = _text(row.get("note") or row.get("observability_duplicate_blocked_phase") or "unknown")
        expr = expression_key(str(row.get("expression") or ""))
        phase_counts[phase] += 1
        if expr:
            expression_counts[expr] += 1
        recent_blocks.append(
            {
                "timestamp": row.get("timestamp", ""),
                "alpha_id": str(row.get("alpha_id") or ""),
                "phase": phase,
                "expression_canonical": expr[:160],
                "family": str(row.get("family") or ""),
                "score": _float_from_any(row.get("score")),
            }
        )
    blocked_count = sum(phase_counts.values())
    top_expressions = [
        {"expression_canonical": expression, "count": count}
        for expression, count in expression_counts.most_common(safe_top_n)
    ]
    return {
        "ok": True,
        "schema_version": "observability_official_call_guard.v1",
        "blocked_count": blocked_count,
        "validation_blocked_count": phase_counts.get("official_validation", 0),
        "simulation_blocked_count": phase_counts.get("official_simulation", 0),
        "phase_counts": dict(phase_counts),
        "top_blocked_expressions": top_expressions,
        "recent_blocks": recent_blocks[-safe_top_n:],
    }


def actionable_duplicate_expression_buckets(rows: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
    """Return duplicate-expression buckets that represent cross-source or cross-alpha history."""
    actionable: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        sources = row.get("sources") if isinstance(row.get("sources"), dict) else {}
        alpha_ids = [str(item) for item in row.get("alpha_ids") or [] if str(item)]
        source_count = _int_from_any(row.get("source_count"))
        has_external_history = source_count >= 2 or any(
            str(source).lower() in {"candidate", "backtest", "submission", "cloud_alpha"}
            for source in sources
        )
        has_cross_alpha_history = len(set(alpha_ids)) >= 2
        if has_external_history or has_cross_alpha_history:
            actionable.append(row)
    return actionable


def actionable_duplicate_expression_records(records: list[dict[str, Any]] | Any, expression: str) -> list[dict[str, Any]]:
    """Return compact exact-match records that should block direct live official calls."""
    target_key = expression_key(expression)
    actionable_sources = {"candidate", "backtest", "submission", "cloud_alpha"}
    rows: list[dict[str, Any]] = []
    seen_alpha_ids = {
        str(row.get("alpha_id") or "")
        for row in records
        if isinstance(row, dict) and str(row.get("alpha_id") or "")
    } if isinstance(records, list) else set()
    for row in records if isinstance(records, list) else []:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").lower()
        row_key = expression_key(str(row.get("expression") or row.get("expression_canonical") or ""))
        if row_key != target_key:
            continue
        if source in actionable_sources or len(seen_alpha_ids) >= 2:
            rows.append(
                {
                    "source": row.get("source", ""),
                    "alpha_id": row.get("alpha_id", ""),
                    "official_alpha_id": row.get("official_alpha_id", ""),
                    "stage": row.get("stage", ""),
                    "status": row.get("status", ""),
                    "timestamp": row.get("timestamp", ""),
                    "expression_canonical": row.get("expression_canonical", ""),
                    "expression_fingerprint": row.get("expression_fingerprint", ""),
                }
            )
    return rows


def diagnose_research_health(
    snapshot: dict[str, Any] | None = None,
    *,
    expression_payload: dict[str, Any] | None = None,
    backtests: dict[str, Any] | None = None,
    errors: dict[str, Any] | None = None,
    jsonl: dict[str, Any] | None = None,
    sqlite_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert observability counters into pre-execution risk diagnostics."""
    snapshot = snapshot or {}
    expression = (
        expression_payload
        if isinstance(expression_payload, dict)
        else snapshot.get("expression_index") if isinstance(snapshot.get("expression_index"), dict) else {}
    )
    backtest_payload = (
        backtests
        if isinstance(backtests, dict)
        else snapshot.get("backtests") if isinstance(snapshot.get("backtests"), dict) else {}
    )
    error_payload = (
        errors
        if isinstance(errors, dict)
        else snapshot.get("errors") if isinstance(snapshot.get("errors"), dict) else {}
    )
    jsonl_payload = (
        jsonl
        if isinstance(jsonl, dict)
        else snapshot.get("jsonl") if isinstance(snapshot.get("jsonl"), dict) else {}
    )
    sqlite_payload = (
        sqlite_cache
        if isinstance(sqlite_cache, dict)
        else snapshot.get("sqlite_cache") if isinstance(snapshot.get("sqlite_cache"), dict) else {}
    )

    total_expression_records = _int_from_any(expression.get("total_expression_records"))
    unique_expression_count = _int_from_any(expression.get("unique_expression_count"))
    duplicate_expression_count = _int_from_any(expression.get("duplicate_expression_count"))
    duplicate_ratio = _float_from_any(expression.get("duplicate_ratio"))
    backtest_total = _int_from_any(backtest_payload.get("total"))
    backtest_failed = _int_from_any(backtest_payload.get("failed_count"))
    backtest_failure_rate = _float_from_any(backtest_payload.get("failure_rate"))
    backtest_retryable = _int_from_any(backtest_payload.get("retryable_count"))
    error_total = _int_from_any(error_payload.get("total"))
    error_retryable = _int_from_any(error_payload.get("retryable_count"))
    error_retryable_rate = _float_from_any(error_payload.get("retryable_rate"))
    category_counts = error_payload.get("category_counts") if isinstance(error_payload.get("category_counts"), dict) else {}
    rate_limit_count = _int_from_any(category_counts.get("rate_limit"))
    jsonl_invalid = sum(
        _int_from_any(row.get("skipped_invalid_count"))
        for row in jsonl_payload.values()
        if isinstance(row, dict)
    )
    jsonl_errors = [
        str(row.get("error") or "").strip()
        for row in jsonl_payload.values()
        if isinstance(row, dict) and str(row.get("error") or "").strip()
    ]
    expression_index_error = str(expression.get("error") or "").strip()

    health_flags: list[str] = []
    warning_flags: list[str] = []
    blocking_flags: list[str] = []
    actions: list[str] = []
    details: dict[str, dict[str, Any]] = {}

    def add_flag(
        flag: str,
        *,
        severity: str = "warning",
        message: str,
        action: str,
        blocking: bool = False,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        health_flags.append(flag)
        if severity in {"warning", "high", "critical"}:
            warning_flags.append(flag)
        if blocking:
            blocking_flags.append(flag)
        actions.append(action)
        details[flag] = {
            "severity": severity,
            "message": message,
            "action": action,
            "evidence": evidence or {},
        }

    if duplicate_expression_count > 0:
        add_flag(
            "duplicate_expression_history",
            severity="warning",
            message="Repeated canonical expression fingerprints were found in local/cloud/backtest history.",
            action="Review duplicate expression fingerprints before submitting new official simulations.",
            evidence={
                "duplicate_expression_count": duplicate_expression_count,
                "duplicate_ratio": duplicate_ratio,
            },
        )
    if expression_index_error:
        add_flag(
            "expression_index_unavailable",
            severity="warning",
            message="The local expression history index could not be built from recent research records.",
            action="Inspect expression-index errors and repair or archive problematic local history rows.",
            evidence={"expression_index_error": expression_index_error},
        )
    if unique_expression_count >= 5 and duplicate_ratio >= 0.25:
        add_flag(
            "high_duplicate_expression_ratio",
            severity="high" if duplicate_ratio >= 0.5 else "warning",
            message="A large share of unique expression fingerprints have repeated records.",
            action="Throttle micro-variant generation and diversify fields/operators before the next candidate batch.",
            evidence={
                "unique_expression_count": unique_expression_count,
                "duplicate_ratio": duplicate_ratio,
            },
        )

    if backtest_total >= 4 and backtest_failure_rate >= 0.25:
        add_flag(
            "backtest_failure_rate_elevated",
            severity="high" if backtest_failure_rate >= 0.5 else "warning",
            message="Recent persisted backtest records show an elevated failure rate.",
            action="Inspect backtest failure patterns and tighten pre-submit validation before more official calls.",
            blocking=backtest_total >= 6 and backtest_failure_rate >= 0.5,
            evidence={
                "backtest_total": backtest_total,
                "failed_count": backtest_failed,
                "failure_rate": backtest_failure_rate,
            },
        )
    if backtest_retryable > 0:
        add_flag(
            "backtest_retryable_errors_present",
            severity="warning",
            message="Backtest records contain retryable official/API failures.",
            action="Keep retry/backoff queues visible and avoid launching a large official batch until retries settle.",
            evidence={"backtest_retryable_count": backtest_retryable},
        )

    if error_retryable > 0:
        add_flag(
            "retryable_official_errors_present",
            severity="warning",
            message="Structured errors include retryable official/API failures.",
            action="Prefer resume/retry workflows over generating more near-duplicate candidates.",
            evidence={
                "retryable_error_count": error_retryable,
                "retryable_error_rate": error_retryable_rate,
            },
        )
    if rate_limit_count > 0:
        add_flag(
            "rate_limit_pressure",
            severity="high" if rate_limit_count >= 3 or error_retryable_rate >= 0.5 else "warning",
            message="Recent errors include rate-limit pressure from official/API calls.",
            action="Pause or slow official/API calls until rate-limit errors clear.",
            blocking=rate_limit_count >= 3 or (error_total >= 4 and error_retryable_rate >= 0.5),
            evidence={
                "rate_limit_count": rate_limit_count,
                "error_total": error_total,
                "retryable_error_rate": error_retryable_rate,
            },
        )

    if jsonl_invalid > 0 or jsonl_errors:
        add_flag(
            "jsonl_history_integrity_warning",
            severity="warning",
            message="One or more local JSONL history files had invalid rows or read errors.",
            action="Repair or archive malformed JSONL rows so local observability remains reliable.",
            evidence={
                "skipped_invalid_count": jsonl_invalid,
                "read_error_count": len(jsonl_errors),
            },
        )
    if sqlite_payload.get("error"):
        add_flag(
            "sqlite_cache_error",
            severity="warning",
            message="The optional SQLite expression cache exists but could not be read.",
            action="Rebuild the SQLite expression cache or fall back to bounded JSONL lookups.",
            evidence={"sqlite_error": sqlite_payload.get("error", "")},
        )
    elif not sqlite_payload.get("exists"):
        health_flags.append("sqlite_cache_missing_optional")
        details["sqlite_cache_missing_optional"] = {
            "severity": "info",
            "message": "The optional SQLite expression cache has not been built.",
            "action": "Optionally build the SQLite expression cache for faster duplicate lookups.",
            "evidence": {"sqlite_cache_exists": False},
        }

    if total_expression_records < 3 and backtest_total < 2:
        health_flags.append("insufficient_local_history")
        details["insufficient_local_history"] = {
            "severity": "info",
            "message": "The local history window is still too small for strong health conclusions.",
            "action": "Run a small local evidence cycle before relying on assistant recommendations.",
            "evidence": {
                "total_expression_records": total_expression_records,
                "backtest_total": backtest_total,
            },
        }
        if not actions:
            actions.append("Run a small local evidence cycle before relying on assistant recommendations.")

    if blocking_flags:
        risk_level = "blocked"
    elif any(details.get(flag, {}).get("severity") == "high" for flag in health_flags):
        risk_level = "high"
    elif warning_flags:
        risk_level = "medium"
    else:
        risk_level = "low"

    if not actions:
        actions.append("No urgent observability alerts in the recent local history window.")

    return {
        "ok": True,
        "schema_version": "research_health_diagnostics.v1",
        "risk_level": risk_level,
        "health_flags": _unique_text_items(health_flags),
        "warning_flags": _unique_text_items(warning_flags),
        "blocking_flags": _unique_text_items(blocking_flags),
        "actions": _unique_text_items(actions),
        "flag_details": details,
        "evidence": {
            "total_expression_records": total_expression_records,
            "unique_expression_count": unique_expression_count,
            "duplicate_expression_count": duplicate_expression_count,
            "duplicate_ratio": duplicate_ratio,
            "backtest_total": backtest_total,
            "backtest_failure_rate": backtest_failure_rate,
            "backtest_retryable_count": backtest_retryable,
            "error_total": error_total,
            "retryable_error_count": error_retryable,
            "retryable_error_rate": error_retryable_rate,
            "rate_limit_count": rate_limit_count,
            "jsonl_invalid_count": jsonl_invalid,
            "jsonl_read_error_count": len(jsonl_errors),
            "sqlite_cache_ready": bool(sqlite_payload.get("exists") and not sqlite_payload.get("error")),
        },
    }


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


def _observability_error_rows(
    backtest_rows: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]],
    check_rows: list[dict[str, Any]],
    job_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source, items in (
        ("backtests", backtest_rows),
        ("lifecycle", lifecycle_rows),
        ("checks", check_rows),
        ("jobs", job_rows),
    ):
        for row in items:
            error = _error_from_observability_row(row)
            if error:
                error_source = _text(row.get("source")) if source == "jobs" else source
                rows.append({"source": error_source or source, **error})
    return rows


def _error_from_observability_row(row: dict[str, Any]) -> dict[str, Any] | None:
    contexts: list[dict[str, Any]] = []
    for key in ("error_context", "error"):
        value = row.get(key)
        if isinstance(value, dict):
            contexts.append(value)
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    value = progress.get("error_context")
    if isinstance(value, dict):
        contexts.append(value)
    for context in contexts:
        payload = {
            **context,
            "alpha_id": row.get("alpha_id") or context.get("alpha_id") or "",
            "timestamp": row.get("timestamp") or row.get("updated_at") or row.get("checked_at") or "",
        }
        payload["message"] = payload.get("error") or payload.get("message") or row.get("note") or ""
        return payload

    message = _text(row.get("error") or row.get("failure_reason"))
    status_text = " ".join(
        _text(row.get(key))
        for key in ("status", "stage", "action", "lifecycle_status", "note")
        if row.get(key) is not None
    )
    if not message and not _looks_failed_status(status_text):
        return None
    exc = RuntimeError(message or status_text or "recorded failure")
    info = classify_error(exc, default_code=_default_error_code_for_row(row))
    payload = info.to_dict()
    payload.update({
        "alpha_id": row.get("alpha_id", ""),
        "timestamp": row.get("timestamp") or row.get("updated_at") or row.get("checked_at") or "",
        "message": payload.get("error", ""),
    })
    return payload


def _default_error_code_for_row(row: dict[str, Any]) -> str:
    text = f"{row.get('action', '')} {row.get('stage', '')} {row.get('status', '')}".upper()
    if "CHECK" in text:
        return "CHECK_ERROR"
    if "SUBMIT" in text:
        return "SUBMIT_ERROR"
    if "SIMULATION" in text or "BACKTEST" in text:
        return "BACKTEST_ERROR"
    return "RECORDED_ERROR"


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
