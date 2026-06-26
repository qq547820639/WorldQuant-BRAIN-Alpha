"""Observability context view and official-call-guard summarization."""

from __future__ import annotations

from collections import Counter
from typing import Any

from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research._observability_helpers import (
    _float_from_any,
    _int_from_any,
    _text,
)
from brain_alpha_ops.research.observability_extensions import (
    optional_observability_context,
)


def observability_context(snapshot: dict[str, Any] | None, *, top_n: int = 10) -> dict[str, Any]:
    """Return a compact LLM-context view of the full observability snapshot."""
    snapshot = snapshot or {}
    expression = snapshot.get("expression_index") if isinstance(snapshot.get("expression_index"), dict) else {}
    backtests = snapshot.get("backtests") if isinstance(snapshot.get("backtests"), dict) else {}
    checks = snapshot.get("checks") if isinstance(snapshot.get("checks"), dict) else {}
    errors = snapshot.get("errors") if isinstance(snapshot.get("errors"), dict) else {}
    official_guard = snapshot.get("official_call_guard") if isinstance(snapshot.get("official_call_guard"), dict) else {}
    sqlite_cache = snapshot.get("sqlite_cache") if isinstance(snapshot.get("sqlite_cache"), dict) else {}
    sqlite_diagnostics = snapshot.get("sqlite_index_diagnostics") if isinstance(snapshot.get("sqlite_index_diagnostics"), dict) else {}
    health = snapshot.get("health") if isinstance(snapshot.get("health"), dict) else {}
    context = {
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
        "check_total": checks.get("total", 0),
        "check_blocked_count": checks.get("blocked_count", 0),
        "cloud_self_correlation_failed_count": checks.get("cloud_self_correlation_failed_count", 0),
        "cloud_self_correlation_block_rate": checks.get("cloud_self_correlation_block_rate", 0.0),
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
        "sqlite_index_update_failure_count": sqlite_diagnostics.get("failure_count", 0),
        "recommended_actions": list(health.get("actions") or snapshot.get("recommendations") or [])[:top_n],
        "recommendations": list(health.get("actions") or snapshot.get("recommendations") or [])[:top_n],
    }
    context.update(optional_observability_context(snapshot, top_n=top_n))
    return context


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
