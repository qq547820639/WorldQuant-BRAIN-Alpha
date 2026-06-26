"""Helper functions and constants for backtest slot payloads.

Split from the former ``web_backtest_slots.py`` monolith (Workstream F3.9).
Holds the official-review blocker classification, slot/row predicates, and
queue-summary helpers used by the route handlers in ``_handlers``.
"""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
)

ReadJsonlRecords = Callable[[str], tuple[list[dict], int, str]]
LoadRunConfig = Callable[[], Any]

_OFFICIAL_REVIEW_LOCAL_BLOCKING_CATEGORIES = {
    "missing",
    "format_error",
    "numeric_out_of_bounds",
    "local_quality_failed",
}
_OFFICIAL_REVIEW_SUBMIT_ONLY_REASON_CODES = {
    "decision_band_not_submit_candidate",
    "gate_not_submission_ready",
    "human_confirmation_required",
    "manual_confirmation_required",
    "missing_official_alpha_id",
    "missing_official_metrics",
    "missing_official_metric_fields",
    "needs_human_confirmation",
    "official_pass_fail_not_pass",
    "expression_too_nested",
}
_OFFICIAL_REVIEW_SUBMIT_ONLY_CATEGORIES = {
    "official_evidence_missing",
    "quality_gate_failed",
}
_OFFICIAL_REVIEW_OFFICIAL_STATE_KEYS = {
    "official_alpha_id": "official_alpha_id_already_present",
    "simulation_id": "official_simulation_already_started",
}


def official_simulation_score_threshold(load_config: LoadRunConfig = load_run_config) -> float:
    try:
        return float(load_config().ops.budget.min_prior_score_for_official_simulation)
    except Exception:
        return 70.0


def slot_score(row: dict) -> float | None:
    for key in ("score", "total_score"):
        value = row.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        return number if number == number else None
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    value = scorecard.get("total_score")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def backtest_task_key(row: dict, index: int) -> str:
    for field in ("simulation_id", "official_alpha_id", "alpha_id"):
        value = str(row.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    action = str(row.get("action") or "").strip()
    timestamp = str(row.get("timestamp") or "").strip()
    if action or timestamp:
        return f"event:{action}:{timestamp}:{index}"
    return ""


def backtest_row_submitted(row: dict) -> bool:
    action = str(row.get("action") or "").lower()
    status = str(row.get("status") or "").upper()
    return action in {"submitted", "completed", "failed", "polling"} or status in {
        "SUBMITTED",
        "RUNNING",
        "PENDING",
        "STARTING",
        "RATE_LIMITED",
        "COMPLETED",
        "FAILED",
        "ERROR",
        "POLL_TIMEOUT",
        "STALL_DETECTED",
        "RESULT_FETCH_FAILED",
    }


def backtest_row_completed(row: dict) -> bool:
    action = str(row.get("action") or "").lower()
    status = str(row.get("status") or "").upper()
    return action == "completed" or status == "COMPLETED"


def backtest_row_failed(row: dict) -> bool:
    action = str(row.get("action") or "").lower()
    status = str(row.get("status") or "").upper()
    return action == "failed" or status in {
        "FAILED",
        "ERROR",
        "POLL_TIMEOUT",
        "STALL_DETECTED",
        "RESULT_FETCH_FAILED",
    }


def backtest_row_pass_verdict(row: dict) -> bool | None:
    for container in (row, row.get("official_metrics"), row.get("metrics")):
        if not isinstance(container, dict):
            continue
        text = str(container.get("pass_fail") or container.get("passFail") or "").upper()
        if text == "PASS":
            return True
        if text == "FAIL":
            return False
    for container in (row.get("gate"), row.get("quality_gate")):
        if not isinstance(container, dict):
            continue
        if container.get("submission_ready") is True:
            return True
        if container.get("submission_ready") is False:
            return False
    return None


def slot_active(status: str | None) -> bool:
    return str(status or "").upper() in {
        "CAPACITY_WAIT",
        "SUBMITTED",
        "RUNNING",
        "PENDING",
        "STARTING",
        "RATE_LIMITED",
        "POLL_ERROR",
    }


def slot_has_official_work_record(slot: dict) -> bool:
    if not isinstance(slot, dict):
        return False
    status = str(slot.get("status") or "").upper()
    if status in {"", "EMPTY", "CAPACITY_WAIT"}:
        return False
    return bool(
        str(slot.get("alpha_id") or "").strip()
        or str(slot.get("simulation_id") or "").strip()
        or str(slot.get("official_alpha_id") or "").strip()
    )


def candidate_score(candidate: dict) -> float:
    scorecard = candidate.get("scorecard") if isinstance(candidate.get("scorecard"), dict) else {}
    value = scorecard.get("total_score", candidate.get("score"))
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return score if score == score else 0.0


def candidate_local_valid(candidate: dict) -> bool:
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    if isinstance(diagnosis.get("local_candidate_valid"), bool):
        return bool(diagnosis.get("local_candidate_valid"))
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    return local_quality.get("passed") is True


def candidate_official_review_blockers(candidate: dict, *, min_score: float) -> list[str]:
    blockers: list[str] = []
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    if diagnosis:
        blockers.extend(quality_diagnosis_official_review_blockers(diagnosis))
    else:
        blockers.append("missing_quality_diagnosis")
    if not candidate_local_valid(candidate):
        blockers.append("local_candidate_invalid")
    if candidate_score(candidate) < min_score:
        blockers.append("score_below_official_simulation_threshold")
    if candidate_local_backtest_failed(candidate):
        blockers.append("local_backtest_failed")
    if high_turnover_generation_risk_reasons(str(candidate.get("expression") or "")):
        blockers.append("high_turnover_generation_risk")
    source_tags = candidate.get("source_tags") if isinstance(candidate.get("source_tags"), list) else []
    if "generation_risk_blocked" in source_tags:
        blockers.append("generation_risk_blocked")
    if candidate_high_cloud_similarity_blocked(candidate):
        blockers.append("high_cloud_similarity")
    for key, reason in _OFFICIAL_REVIEW_OFFICIAL_STATE_KEYS.items():
        if str(candidate.get(key) or "").strip():
            blockers.append(reason)
    if isinstance(candidate.get("official_metrics"), dict) and candidate.get("official_metrics"):
        blockers.append("official_simulation_already_completed")
    return sorted(set(blockers))


def quality_diagnosis_official_review_blockers(diagnosis: dict) -> list[str]:
    blockers: list[str] = []
    reason_rows = diagnosis.get("reasons") if isinstance(diagnosis.get("reasons"), list) else []
    if reason_rows:
        for row in reason_rows:
            if not isinstance(row, dict) or row.get("severity") != "blocking":
                continue
            code = str(row.get("code") or "")
            category = str(row.get("category") or "")
            if not code or is_submit_only_quality_reason(code, category):
                continue
            if category in _OFFICIAL_REVIEW_LOCAL_BLOCKING_CATEGORIES and not code.startswith("official_"):
                blockers.append(code)
        return blockers
    for reason in diagnosis.get("blocking_reasons") or []:
        code = str(reason or "")
        if code and not is_submit_only_quality_reason(code, "") and not code.startswith("official_"):
            blockers.append(code)
    return blockers


def candidate_submit_evidence_blockers(candidate: dict) -> list[str]:
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    blockers: list[str] = []
    if diagnosis:
        reason_rows = diagnosis.get("reasons") if isinstance(diagnosis.get("reasons"), list) else []
        if reason_rows:
            for row in reason_rows:
                if not isinstance(row, dict) or row.get("severity") != "blocking":
                    continue
                code = str(row.get("code") or "")
                category = str(row.get("category") or "")
                if code and is_submit_only_quality_reason(code, category):
                    blockers.append(code)
        else:
            for reason in diagnosis.get("blocking_reasons") or []:
                code = str(reason or "")
                if code and is_submit_only_quality_reason(code, ""):
                    blockers.append(code)
    return sorted(set(blockers))


def is_submit_only_quality_reason(code: str, category: str) -> bool:
    if code in _OFFICIAL_REVIEW_SUBMIT_ONLY_REASON_CODES:
        return True
    if category in _OFFICIAL_REVIEW_SUBMIT_ONLY_CATEGORIES:
        return True
    return False


def candidate_high_cloud_similarity_blocked(candidate: dict) -> bool:
    status = str(candidate.get("lifecycle_status") or "").lower()
    if "high_cloud_similarity" in status:
        return True
    risk = candidate.get("cloud_correlation_risk") if isinstance(candidate.get("cloud_correlation_risk"), dict) else {}
    level = str(risk.get("level") or "").lower()
    return level in {"high", "blocked"}


def candidate_local_backtest_failed(candidate: dict) -> bool:
    for container_key in ("local_quality", "submission", "extra_fields"):
        container = candidate.get(container_key)
        if not isinstance(container, dict):
            continue
        local_backtest = container.get("local_backtest")
        if (
            isinstance(local_backtest, dict)
            and local_backtest.get("pass_local") is False
            and local_backtest.get("advisory") is not True
        ):
            return True
    local_backtest = candidate.get("local_backtest")
    return (
        isinstance(local_backtest, dict)
        and local_backtest.get("pass_local") is False
        and local_backtest.get("advisory") is not True
    )


def backtest_queue_next_action(*, candidate_count: int, review_candidate_count: int, open_slot_count: int) -> str:
    if candidate_count <= 0:
        return "generate_candidates"
    if review_candidate_count > 0 and open_slot_count > 0:
        return "trusted_environment_official_simulation_required"
    if review_candidate_count > 0:
        return "wait_for_open_backtest_slot"
    return "improve_or_regenerate_candidates"
