"""Backtest slot payload and queue-summary route handlers.

Split from the former ``web_backtest_slots.py`` monolith (Workstream F3.9).
Builds the per-slot payload, status board, and local-readonly queue summary
served by the Web routes. Classification helpers live in ``_helpers``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from brain_alpha_ops.config import load_run_config

from ._helpers import (
    LoadRunConfig,
    ReadJsonlRecords,
    backtest_queue_next_action,
    backtest_row_completed,
    backtest_row_failed,
    backtest_row_pass_verdict,
    backtest_row_submitted,
    backtest_task_key,
    candidate_local_valid,
    candidate_official_review_blockers,
    candidate_score,
    candidate_submit_evidence_blockers,
    official_simulation_score_threshold,
    slot_active,
    slot_has_official_work_record,
    slot_score,
)


def backtest_slot_limit(load_config: LoadRunConfig = load_run_config) -> int:
    """Return the official simulation slot limit (Workstream C1.2).

    Unified to ``OFFICIAL_SIMULATION_SLOT_LIMIT`` (single source of truth).
    Budget fields may LOWER the limit but can never RAISE it above 3.
    """
    from brain_alpha_ops.research.simulation_scheduler._consistency import (
        OFFICIAL_SIMULATION_SLOT_LIMIT,
    )
    try:
        budget = load_config().ops.budget
        return min(
            OFFICIAL_SIMULATION_SLOT_LIMIT,
            max(1, int(budget.official_backtest_batch_size)),
            max(1, int(budget.max_official_simulations_per_cycle)),
            max(1, int(budget.max_official_concurrent_simulations)),
        )
    except Exception:
        return OFFICIAL_SIMULATION_SLOT_LIMIT


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
