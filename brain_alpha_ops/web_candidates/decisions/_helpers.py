"""Helper utilities for candidate production decisions."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.redaction import redact_text

_ARCHIVE_STATUS_TOKENS = (
    "local_prefilter_rejected",
    "local_standard_rejected",
    "official_standard_rejected",
    "candidate_pool_pruned",
    "high_cloud_similarity",
    "hard_gate_blocked",
    "rejected",
    "failed",
)
_GENERIC_POOL_STATUSES = {
    "",
    "created",
    "candidate_pool_retained",
    "locally_scored",
}


def _is_submit_only_quality_reason(code: str, category: str = "") -> bool:
    """Lazy import wrapper avoiding circular import through web_backtest_slots."""
    from brain_alpha_ops.web.misc.web_backtest_slots import is_submit_only_quality_reason as _fn

    return _fn(code, category)


def candidate_submission_ready(row: dict[str, Any]) -> bool:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return bool(
        str(row.get("lifecycle_status") or "").lower() == "submission_ready"
        or diagnosis.get("submission_ready") is True
        or gate.get("submission_ready") is True
    )


def candidate_score(row: dict[str, Any]) -> float:
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    try:
        value = float(scorecard.get("total_score", row.get("score")) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return value if value == value else 0.0


def candidate_has_official_evidence(row: dict[str, Any]) -> bool:
    return bool(
        str(row.get("official_alpha_id") or "").strip()
        or str(row.get("simulation_id") or "").strip()
        or (isinstance(row.get("official_metrics"), dict) and bool(row.get("official_metrics")))
    )


def candidate_submit_only_reasons(row: dict[str, Any]) -> list[str]:
    return sorted({
        code
        for code, category in _blocking_pairs(row)
        if _is_submit_only_quality_reason(code, category)
    } | {
        reason
        for reason in _gate_failed_reasons(row)
        if _is_submit_only_quality_reason(reason, "")
    })


def candidate_hard_blocking_reasons(row: dict[str, Any]) -> list[str]:
    reasons: set[str] = set()
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        reasons.add("local_quality_failed")
    local_backtest = local_quality.get("local_backtest") if isinstance(local_quality.get("local_backtest"), dict) else {}
    if local_backtest.get("pass_local") is False:
        reasons.add("local_backtest_failed")
    for code, category in _blocking_pairs(row):
        if not _is_submit_only_quality_reason(code, category):
            reasons.add(code)
    for reason in _gate_failed_reasons(row):
        if not _is_submit_only_quality_reason(reason, ""):
            reasons.add(reason)
    return sorted(reason for reason in reasons if reason)


def _lifecycle_text(value: Any, *, default: str = "", max_length: int = 160) -> str:
    return redact_text(value if value is not None else default, max_length=max_length).strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _status(row: dict[str, Any]) -> str:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return str(row.get("lifecycle_status") or diagnosis.get("status") or gate.get("status") or "").strip().lower()


def _decision_band(row: dict[str, Any]) -> str:
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    return str(scorecard.get("decision_band") or row.get("decision_band") or "").strip()


def _blocking_pairs(row: dict[str, Any]) -> list[tuple[str, str]]:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    pairs: set[tuple[str, str]] = set()
    primary = diagnosis.get("primary_reason") if isinstance(diagnosis.get("primary_reason"), dict) else {}
    code = str(primary.get("code") or "").strip()
    if code:
        pairs.add((code, str(primary.get("category") or "").strip()))
    for reason in diagnosis.get("blocking_reasons") or []:
        text = str(reason or "").strip()
        if text:
            pairs.add((text, ""))
    reason_rows = diagnosis.get("reasons") if isinstance(diagnosis.get("reasons"), list) else []
    for item in reason_rows:
        if not isinstance(item, dict):
            continue
        if item.get("severity") and item.get("severity") != "blocking":
            continue
        code = str(item.get("code") or "").strip()
        if code:
            pairs.add((code, str(item.get("category") or "").strip()))
    return sorted(pairs)


def _gate_failed_reasons(row: dict[str, Any]) -> list[str]:
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return sorted({
        str(reason or "").strip()
        for reason in gate.get("failed_reasons") or []
        if str(reason or "").strip()
    })


def _has_human_confirmation_blocker(row: dict[str, Any]) -> bool:
    reasons = set(candidate_submit_only_reasons(row))
    return bool(reasons & {"needs_human_confirmation", "human_confirmation_required", "manual_confirmation_required"})


def _only_official_evidence_missing(row: dict[str, Any]) -> bool:
    hard = candidate_hard_blocking_reasons(row)
    if hard:
        return False
    submit_only = set(candidate_submit_only_reasons(row))
    return bool(submit_only & {"missing_official_alpha_id", "missing_official_metrics", "missing_official_metric_fields"})
