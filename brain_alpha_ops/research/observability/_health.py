"""Research health diagnostics from observability counters."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research._observability_helpers import (
    _float_from_any,
    _int_from_any,
    _unique_text_items,
)
from brain_alpha_ops.research.observability_extensions import (
    optional_research_health_payload,
)


def diagnose_research_health(
    snapshot: dict[str, Any] | None = None,
    *,
    expression_payload: dict[str, Any] | None = None,
    backtests: dict[str, Any] | None = None,
    checks: dict[str, Any] | None = None,
    errors: dict[str, Any] | None = None,
    jsonl: dict[str, Any] | None = None,
    sqlite_cache: dict[str, Any] | None = None,
    sqlite_index_diagnostics: dict[str, Any] | None = None,
    market_data_cache: dict[str, Any] | None = None,
    alerts: dict[str, Any] | None = None,
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
    check_payload = (
        checks
        if isinstance(checks, dict)
        else snapshot.get("checks") if isinstance(snapshot.get("checks"), dict) else {}
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
    sqlite_diagnostics_payload = (
        sqlite_index_diagnostics
        if isinstance(sqlite_index_diagnostics, dict)
        else snapshot.get("sqlite_index_diagnostics") if isinstance(snapshot.get("sqlite_index_diagnostics"), dict) else {}
    )
    market_cache_payload = (
        market_data_cache
        if isinstance(market_data_cache, dict)
        else snapshot.get("market_data_cache") if isinstance(snapshot.get("market_data_cache"), dict) else {}
    )
    alert_payload = (
        alerts
        if isinstance(alerts, dict)
        else snapshot.get("alerts") if isinstance(snapshot.get("alerts"), dict) else {}
    )

    total_expression_records = _int_from_any(expression.get("total_expression_records"))
    unique_expression_count = _int_from_any(expression.get("unique_expression_count"))
    duplicate_expression_count = _int_from_any(expression.get("duplicate_expression_count"))
    duplicate_ratio = _float_from_any(expression.get("duplicate_ratio"))
    backtest_total = _int_from_any(backtest_payload.get("total"))
    backtest_failed = _int_from_any(backtest_payload.get("failed_count"))
    backtest_failure_rate = _float_from_any(backtest_payload.get("failure_rate"))
    backtest_retryable = _int_from_any(backtest_payload.get("retryable_count"))
    check_total = _int_from_any(check_payload.get("total"))
    check_blocked = _int_from_any(check_payload.get("blocked_count"))
    cloud_self_correlation_failed = _int_from_any(check_payload.get("cloud_self_correlation_failed_count"))
    cloud_self_correlation_rate = _float_from_any(check_payload.get("cloud_self_correlation_block_rate"))
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
    sqlite_index_update_failures = _int_from_any(sqlite_diagnostics_payload.get("failure_count"))

    health_flags: list[str] = []
    warning_flags: list[str] = []
    blocking_flags: list[str] = []
    actions: list[str] = []
    details: dict[str, dict[str, Any]] = {}
    optional_payload = optional_research_health_payload(market_cache_payload, alert_payload)
    health_flags.extend(optional_payload["health_flags"])
    actions.extend(optional_payload["actions"])
    details.update(optional_payload["details"])

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

    if check_total >= 10 and cloud_self_correlation_failed > 0 and cloud_self_correlation_rate >= 0.5:
        add_flag(
            "cloud_self_correlation_saturation",
            severity="critical" if cloud_self_correlation_rate >= 0.8 else "high",
            message="Recent official check records are dominated by cloud_self_correlation blocks.",
            action="Pause submission, refresh cloud context, diversify expression templates, then rerun checks before submitting.",
            blocking=check_total >= 20 and cloud_self_correlation_rate >= 0.8,
            evidence={
                "check_total": check_total,
                "blocked_count": check_blocked,
                "cloud_self_correlation_failed_count": cloud_self_correlation_failed,
                "cloud_self_correlation_block_rate": cloud_self_correlation_rate,
                "top_failed_rules": list(check_payload.get("top_failed_rules") or [])[:5],
            },
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
    if sqlite_index_update_failures > 0:
        add_flag(
            "sqlite_index_incremental_update_failed",
            severity="warning",
            message="Incremental SQLite research index updates failed after JSONL writes succeeded.",
            action="Rebuild the SQLite research indexes or continue with bounded JSONL lookups until the cache is healthy.",
            evidence={
                "failure_count": sqlite_index_update_failures,
                "component_counts": sqlite_diagnostics_payload.get("component_counts", {}),
                "source_file_counts": sqlite_diagnostics_payload.get("source_file_counts", {}),
            },
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
    elif any(details.get(flag, {}).get("severity") in {"high", "critical"} for flag in health_flags):
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
            "check_total": check_total,
            "check_blocked_count": check_blocked,
            "cloud_self_correlation_failed_count": cloud_self_correlation_failed,
            "cloud_self_correlation_block_rate": cloud_self_correlation_rate,
            "error_total": error_total,
            "retryable_error_count": error_retryable,
            "retryable_error_rate": error_retryable_rate,
            "rate_limit_count": rate_limit_count,
            "jsonl_invalid_count": jsonl_invalid,
            "jsonl_read_error_count": len(jsonl_errors),
            "sqlite_cache_ready": bool(sqlite_payload.get("exists") and not sqlite_payload.get("error")),
            "sqlite_index_update_failure_count": sqlite_index_update_failures,
            **optional_payload["evidence"],
        },
    }
