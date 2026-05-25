"""Robustness evidence extraction for assistant context packs."""

from __future__ import annotations

import math
from typing import Any


def latest_candidate_rows(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    snapshot = snapshot or {}
    result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
    progress = snapshot.get("progress") if isinstance(snapshot.get("progress"), dict) else {}
    summary = _first_dict(result.get("summary"), progress.get("data"), snapshot.get("summary"))
    rows: list[dict[str, Any]] = []
    for container in (result, summary, snapshot):
        if not isinstance(container, dict):
            continue
        for key in ("candidates", "passed_candidates", "pending_backtest_candidates", "submitted_candidates"):
            rows.extend(_first_list(container.get(key)))
    return _dedupe_candidate_rows(rows)


def build_robustness_context(candidates: list[dict[str, Any]], *, top_n: int) -> dict[str, Any]:
    anti_rows = [
        row for row in (_report_brief(candidate, "anti_overfit_report", status_key="recommendation") for candidate in candidates)
        if row
    ]
    rolling_rows = [
        row for row in (_report_brief(candidate, "rolling_validation_report", status_key="status") for candidate in candidates)
        if row
    ]
    anti_status_counts = _status_counts(anti_rows, "recommendation")
    rolling_status_counts = _status_counts(rolling_rows, "status")
    flags: list[str] = []
    actions: list[str] = []
    if anti_status_counts.get("block"):
        flags.append("anti_overfit_block")
        actions.append("Revise or discard candidates with anti-overfit recommendation=block before official simulation.")
    if anti_status_counts.get("caution"):
        flags.append("anti_overfit_caution")
        actions.append("Require stronger robustness evidence before ranking caution candidates for submission.")
    if rolling_status_counts.get("fail") or rolling_status_counts.get("insufficient_data"):
        flags.append("rolling_validation_weak")
        actions.append("Prefer candidates with stable rolling validation before spending more official budget.")
    return {
        "schema_version": "assistant_robustness_context.v1",
        "candidate_count": len(candidates),
        "anti_overfit": {
            "available_count": len(anti_rows),
            "status_counts": anti_status_counts,
            "avg_score": _average_report_score(anti_rows),
            "top_reports": anti_rows[:top_n],
        },
        "rolling_validation": {
            "available_count": len(rolling_rows),
            "status_counts": rolling_status_counts,
            "avg_score": _average_report_score(rolling_rows),
            "top_reports": rolling_rows[:top_n],
        },
        "risk_flags": _unique_text_items(flags),
        "recommended_actions": _unique_text_items(actions),
    }


def format_report_status(group: dict[str, Any], status_key: str) -> str:
    available = _int_value(group.get("available_count"))
    counts = group.get("status_counts") if isinstance(group.get("status_counts"), dict) else {}
    if not available:
        return "none"
    parts = [f"available={available}"]
    for key, count in sorted(counts.items()):
        parts.append(f"{status_key}:{key}={count}")
    avg_score = _float_value(group.get("avg_score"))
    if avg_score:
        parts.append(f"avg_score={avg_score}")
    return ", ".join(parts)


def assistant_robustness_signals(robustness: dict[str, Any]) -> dict[str, Any]:
    robustness = robustness if isinstance(robustness, dict) else {}
    anti = robustness.get("anti_overfit") if isinstance(robustness.get("anti_overfit"), dict) else {}
    rolling = robustness.get("rolling_validation") if isinstance(robustness.get("rolling_validation"), dict) else {}
    return {
        "anti": anti,
        "rolling": rolling,
        "flags": _unique_text_items(robustness.get("risk_flags") or []),
        "actions": _unique_text_items(robustness.get("recommended_actions") or []),
        "anti_available": _int_value(anti.get("available_count")),
        "rolling_available": _int_value(rolling.get("available_count")),
    }


def robustness_gate_adjustment(signals: dict[str, Any]) -> dict[str, Any] | None:
    anti_available = _int_value(signals.get("anti_available"))
    rolling_available = _int_value(signals.get("rolling_available"))
    if not anti_available and not rolling_available:
        return None
    anti = signals.get("anti") if isinstance(signals.get("anti"), dict) else {}
    rolling = signals.get("rolling") if isinstance(signals.get("rolling"), dict) else {}
    return {
        "target": "robustness_gate",
        "value": {
            "anti_overfit_available_count": anti_available,
            "rolling_validation_available_count": rolling_available,
            "anti_overfit_status_counts": anti.get("status_counts") or {},
            "rolling_validation_status_counts": rolling.get("status_counts") or {},
        },
        "rationale": "Anti-overfit and rolling-validation evidence should gate candidate priority before official API budget is used.",
    }


def robustness_evidence(signals: dict[str, Any]) -> dict[str, Any]:
    anti = signals.get("anti") if isinstance(signals.get("anti"), dict) else {}
    rolling = signals.get("rolling") if isinstance(signals.get("rolling"), dict) else {}
    return {
        "anti_overfit_available_count": _int_value(signals.get("anti_available")),
        "rolling_validation_available_count": _int_value(signals.get("rolling_available")),
        "robustness_risk_flags": _unique_text_items(signals.get("flags") or []),
        "anti_overfit_status_counts": anti.get("status_counts") or {},
        "rolling_validation_status_counts": rolling.get("status_counts") or {},
    }


def _dedupe_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = str(row.get("alpha_id") or row.get("official_alpha_id") or row.get("simulation_id") or row.get("expression") or "")
        if not key:
            key = str(len(unique))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _report_brief(candidate: dict[str, Any], report_key: str, *, status_key: str) -> dict[str, Any]:
    report = _candidate_report(candidate, report_key)
    if not report:
        return {}
    tests = report.get("tests") if isinstance(report.get("tests"), list) else []
    failed_tests = [
        str(test.get("name") or "")
        for test in tests
        if isinstance(test, dict) and test.get("passed") is False and str(test.get("name") or "")
    ]
    return {
        "alpha_id": str(candidate.get("alpha_id") or candidate.get("official_alpha_id") or candidate.get("simulation_id") or ""),
        status_key: str(report.get(status_key) or report.get("recommendation") or report.get("status") or ""),
        "score": _float_value(report.get("score")),
        "passed": report.get("passed"),
        "sample_size": _int_value(report.get("sample_size")),
        "failed_tests": failed_tests[:5],
    }


def _candidate_report(candidate: dict[str, Any], report_key: str) -> dict[str, Any]:
    submission = candidate.get("submission") if isinstance(candidate.get("submission"), dict) else {}
    scorecard = candidate.get("scorecard") if isinstance(candidate.get("scorecard"), dict) else {}
    for container in (submission, scorecard, candidate):
        report = container.get(report_key) if isinstance(container, dict) else None
        if isinstance(report, dict):
            return report
    return {}


def _status_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get(key) or "").strip().lower()
        if not status:
            continue
        counts[status] = counts.get(status, 0) + 1
    return counts


def _average_report_score(rows: list[dict[str, Any]]) -> float:
    scores = [_float_value(row.get("score")) for row in rows if row.get("score") is not None]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _first_list(*values: Any) -> list[dict[str, Any]]:
    for value in values:
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _unique_text_items(rows: list[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in rows:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return round(number, 4)
