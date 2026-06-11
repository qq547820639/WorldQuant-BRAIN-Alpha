"""Backtest slot payload and queue-summary helpers for Web routes."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.research.fallback_generation import high_turnover_generation_risk_reasons

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
    "missing_official_alpha_id",
    "missing_official_metrics",
    "missing_official_metric_fields",
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


def backtest_slot_limit(load_config: LoadRunConfig = load_run_config) -> int:
    try:
        budget = load_config().ops.budget
        return max(
            3,
            min(
                max(1, int(budget.official_backtest_batch_size)),
                max(1, int(budget.max_official_simulations_per_cycle)),
                max(1, int(budget.max_official_concurrent_simulations)),
            ),
        )
    except Exception:
        return 3


def backtest_slots_payload(
    read_jsonl_records: ReadJsonlRecords,
    *,
    load_config: LoadRunConfig = load_run_config,
) -> dict:
    slot_limit = backtest_slot_limit(load_config)
    rows, total, path = read_jsonl_records("backtests.jsonl")
    latest_by_slot: dict[int, dict] = {}
    rows_by_slot: dict[int, list[dict]] = {}
    for row in rows:
        try:
            slot = int(row.get("slot") or 0)
        except (TypeError, ValueError):
            continue
        if 1 <= slot <= slot_limit:
            rows_by_slot.setdefault(slot, []).append(row)
            latest_by_slot[slot] = row
    slots = [
        slot_payload(slot, latest_by_slot.get(slot), rows_by_slot.get(slot, []))
        for slot in range(1, slot_limit + 1)
    ]
    active_count = sum(1 for slot in slots if slot_active(slot.get("status")))
    return {
        "ok": True,
        "source": "backtests_jsonl",
        "path": path,
        "record_count": total,
        "slot_limit": slot_limit,
        "active_count": active_count,
        "queue_summary": backtest_queue_summary(
            slots,
            slot_limit=slot_limit,
            active_count=active_count,
            read_jsonl_records=read_jsonl_records,
            min_score=official_simulation_score_threshold(load_config),
        ),
        "slots": slots,
        "updated_at": max((str(row.get("timestamp") or "") for row in latest_by_slot.values()), default=""),
    }


def slot_payload(slot: int, row: dict | None, slot_rows: list[dict] | None = None) -> dict:
    rows = slot_rows or []
    if not row:
        return {
            "slot": slot,
            "status": "empty",
            "alpha_id": "",
            "expression": "",
            "status_board": backtest_status_board(slot, None, rows),
        }
    return {
        "slot": slot,
        "status": row.get("status", "unknown"),
        "alpha_id": row.get("alpha_id", ""),
        "official_alpha_id": row.get("official_alpha_id", ""),
        "simulation_id": row.get("simulation_id", ""),
        "expression": row.get("expression", ""),
        "sharpe": row.get("sharpe"),
        "fitness": row.get("fitness"),
        "turnover": row.get("turnover"),
        "score": slot_score(row),
        "progress": row.get("progress"),
        "progress_percent": row.get("progress_percent", row.get("progress")),
        "poll_count": row.get("poll_count"),
        "next_poll_seconds": row.get("next_poll_seconds"),
        "message": row.get("message", ""),
        "official_metrics": row.get("official_metrics", {}),
        "gate": row.get("gate", {}),
        "error": row.get("error"),
        "timestamp": row.get("timestamp"),
        "status_board": backtest_status_board(slot, row, rows),
    }


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


def backtest_status_board(slot: int, latest_row: dict | None, rows: list[dict]) -> dict:
    tasks: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        key = backtest_task_key(row, index)
        if not key:
            continue
        task = tasks.setdefault(key, {"submitted": False, "completed": False, "failed": False, "passed": None})
        if backtest_row_submitted(row):
            task["submitted"] = True
        if backtest_row_completed(row):
            task["submitted"] = True
            task["completed"] = True
        if backtest_row_failed(row):
            task["submitted"] = True
            task["failed"] = True
        verdict = backtest_row_pass_verdict(row)
        if verdict is not None:
            task["passed"] = bool(verdict)

    submitted_count = sum(1 for task in tasks.values() if task["submitted"])
    completed_count = sum(1 for task in tasks.values() if task["completed"])
    failed_count = sum(1 for task in tasks.values() if task["failed"])
    passed_count = sum(1 for task in tasks.values() if task["passed"] is True)
    not_passed_count = sum(1 for task in tasks.values() if task["passed"] is False or (task["failed"] and task["passed"] is None))
    verdict_count = passed_count + not_passed_count
    return {
        "task_index": slot,
        "alpha_id": (latest_row or {}).get("alpha_id", ""),
        "submitted_count": submitted_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "passed_count": passed_count,
        "not_passed_count": not_passed_count,
        "pass_rate": round(passed_count / verdict_count, 4) if verdict_count else 0.0,
    }


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


def backtest_queue_summary(
    slots: list[dict],
    *,
    slot_limit: int,
    active_count: int,
    read_jsonl_records: ReadJsonlRecords,
    min_score: float,
) -> dict:
    candidates, candidate_total, candidate_path = read_jsonl_records("candidates.jsonl")
    reason_counts: Counter[str] = Counter()
    local_valid_count = 0
    above_score_count = 0
    review_candidate_count = 0
    submit_reason_counts: Counter[str] = Counter()
    submit_evidence_blocking_count = 0
    for candidate in candidates:
        score = candidate_score(candidate)
        if candidate_local_valid(candidate):
            local_valid_count += 1
        if score >= min_score:
            above_score_count += 1
        blockers = candidate_official_review_blockers(candidate, min_score=min_score)
        submit_blockers = candidate_submit_evidence_blockers(candidate)
        if submit_blockers:
            submit_evidence_blocking_count += 1
            submit_reason_counts.update(submit_blockers)
        if blockers:
            reason_counts.update(blockers)
        else:
            review_candidate_count += 1
    open_slot_count = max(0, int(slot_limit or 0) - int(active_count or 0))
    official_slot_record_count = sum(1 for slot in slots if slot_has_official_work_record(slot))
    return {
        "schema_version": "backtest-slot-queue-summary-v1",
        "source": "local_readonly_snapshot",
        "official_api_called": False,
        "official_slot_record_count": official_slot_record_count,
        "candidate_path": candidate_path,
        "candidate_count": candidate_total,
        "returned_candidate_count": len(candidates),
        "slot_limit": slot_limit,
        "active_slot_count": active_count,
        "open_slot_count": open_slot_count,
        "empty_slot_count": sum(1 for slot in slots if str(slot.get("status") or "").upper() == "EMPTY"),
        "local_valid_count": local_valid_count,
        "above_simulation_score_count": above_score_count,
        "review_candidate_count": review_candidate_count,
        "blocked_candidate_count": max(0, len(candidates) - review_candidate_count),
        "submit_evidence_blocking_count": submit_evidence_blocking_count,
        "min_prior_score_for_official_simulation": min_score,
        "top_blocking_reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "top_submit_blocking_reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(submit_reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "next_action": backtest_queue_next_action(
            candidate_count=candidate_total,
            review_candidate_count=review_candidate_count,
            open_slot_count=open_slot_count,
        ),
    }


def official_simulation_score_threshold(load_config: LoadRunConfig = load_run_config) -> float:
    try:
        return float(load_config().ops.budget.min_prior_score_for_official_simulation)
    except Exception:
        return 70.0


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
