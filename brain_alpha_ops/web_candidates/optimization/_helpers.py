"""Candidate inspection and utility helpers for optimization."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_candidates.decisions import candidate_decision_action


def _candidate_needs_optimization(row: dict[str, Any]) -> bool:
    if _candidate_rejected_by_local_gate(row):
        return False
    if _candidate_submission_ready(row):
        return False
    return candidate_decision_action(row) == "optimize"


def _candidate_submission_ready(row: dict[str, Any]) -> bool:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return bool(
        str(row.get("lifecycle_status") or "").lower() == "submission_ready"
        or diagnosis.get("submission_ready") is True
        or gate.get("submission_ready") is True
    )


def _candidate_rejected_by_local_gate(candidate: dict[str, Any]) -> bool:
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    if diagnosis.get("local_candidate_valid") is False:
        return True
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        return True
    support = local_quality.get("local_backtest_support") if isinstance(local_quality.get("local_backtest_support"), dict) else {}
    if support.get("supported") is False:
        return True
    local_backtest = local_quality.get("local_backtest") if isinstance(local_quality.get("local_backtest"), dict) else {}
    if local_backtest.get("pass_local") is False:
        return True
    return False


def _candidate_rejection_reasons(candidate: dict[str, Any]) -> list[str]:
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    reasons = [str(reason or "").strip() for reason in diagnosis.get("blocking_reasons") or [] if str(reason or "").strip()]
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    for reason in local_quality.get("reasons") or []:
        text = str(reason or "").strip()
        if text:
            reasons.append(text.split(":", 1)[0])
    local_backtest = local_quality.get("local_backtest") if isinstance(local_quality.get("local_backtest"), dict) else {}
    if local_backtest.get("pass_local") is False:
        reasons.append("local_backtest_failed")
    return sorted(set(reasons)) or ["local_candidate_invalid"]


def _rejected_reason_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        for reason in _candidate_rejection_reasons(candidate):
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _candidate_score(row: dict[str, Any]) -> float:
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    try:
        value = float(scorecard.get("total_score", row.get("score")) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return value if value == value else 0.0


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    results: list[int] = []
    for item in value:
        try:
            results.append(int(item))
        except (TypeError, ValueError):
            continue
    return results


def _candidate_blocking_codes(row: dict[str, Any]) -> list[str]:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    codes: set[str] = set()
    primary = diagnosis.get("primary_reason") if isinstance(diagnosis.get("primary_reason"), dict) else {}
    primary_code = str(primary.get("code") or "").strip()
    if primary_code:
        codes.add(primary_code)
    for reason in diagnosis.get("blocking_reasons") or []:
        text = str(reason or "").strip()
        if text:
            codes.add(text)
    for item in diagnosis.get("reasons") or []:
        if not isinstance(item, dict):
            continue
        if item.get("severity") and item.get("severity") != "blocking":
            continue
        code = str(item.get("code") or "").strip()
        if code:
            codes.add(code)
    return sorted(codes)


def _is_submit_only_blocker(reason: str) -> bool:
    from brain_alpha_ops.web.misc.web_backtest_slots import is_submit_only_quality_reason

    return is_submit_only_quality_reason(reason, "")


def _expression_key(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
