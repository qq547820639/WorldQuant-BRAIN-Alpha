"""Result handlers for official simulation polling.

Extracted from the polling loop in ``simulate_candidates_job`` to keep
individual modules focused and under the line-budget.
"""

from __future__ import annotations

import time
from typing import Any

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.web_candidates.audit import append_scientific_audit_event
from brain_alpha_ops.web_candidates.simulation_failures import (
    simulation_failure_evidence as _simulation_failure_evidence,
)
from brain_alpha_ops.web_candidates.simulation_runtime import _progress_percent
from brain_alpha_ops.web_candidates.simulation_state import (
    append_backtest_record as _append_backtest_record,
    clear_candidate_simulation_cooldown as _clear_candidate_simulation_cooldown,
    save_candidate_update as _save_candidate_update,
    score_simulated_candidate as _score_simulated_candidate,
)


def _handle_completed_result(
    state: Any,
    slot: dict[str, Any],
    *,
    poll_attempt: int,
    status_elapsed: float,
) -> None:
    """Handle a COMPLETED simulation: fetch result, re-score, update state."""
    candidate = slot["candidate"]
    alpha_id = str(slot["alpha_id"])
    expression = str(slot["expression"])
    sim_id = str(slot["simulation_id"])
    i = int(slot["slot_index"])
    try:
        result = state.api.fetch_result(sim_id)
        candidate["official_alpha_id"] = result.get("alpha_id", "") or result.get("metrics", {}).get("official_alpha_id", "")
        candidate["official_metrics"] = result.get("metrics", {})
        candidate["lifecycle_status"] = "official_simulated"
        candidate = append_scientific_audit_event(
            candidate,
            operation="official_simulation_writeback",
            source="web_official_simulation_result",
            feedback_sources=["official_simulation_result", "scorecard"],
            official_api_called=True,
            details={
                "status": "COMPLETED",
                "simulation_id": sim_id,
                "official_alpha_id": candidate.get("official_alpha_id", ""),
            },
        )
        _clear_candidate_simulation_cooldown(candidate)
        state.last_activity = time.monotonic()

        # Re-score with official metrics
        try:
            rescored = _score_simulated_candidate(candidate, state.config)
            candidate.clear()
            candidate.update(rescored)
        except Exception as score_exc:
            state.log.warning("Re-scoring failed for %s: %s", redact_text(alpha_id), redact_error_message(score_exc))
        else:
            candidate = append_scientific_audit_event(
                candidate,
                operation="official_simulation_writeback",
                source="web_official_rescore",
                feedback_sources=["official_metrics", "scorecard", "quality_gate"],
                official_api_called=False,
                details={"status": "RESCORED", "simulation_id": sim_id},
            )

        state.completed += 1
        state.results.append({
            "alpha_id": alpha_id,
            "official_alpha_id": candidate.get("official_alpha_id", ""),
            "simulation_id": sim_id,
            "status": "completed",
            "official_metrics": {k: v for k, v in candidate.get("official_metrics", {}).items() if k != "raw"},
        })

        _append_backtest_record(state.storage_dir, {
            "action": "completed",
            "slot": i + 1,
            "alpha_id": alpha_id,
            "official_alpha_id": candidate.get("official_alpha_id", ""),
            "simulation_id": sim_id,
            "status": "COMPLETED",
            "expression": expression,
            "official_metrics": candidate.get("official_metrics", {}),
            "poll_count": poll_attempt,
            "poll_elapsed_seconds": round(max(0.0, status_elapsed), 1),
            "next_poll_seconds": 0.0,
            "progress_percent": 100,
            "message": f"官方模拟完成，已等待 {status_elapsed:.1f} 秒。",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        })
        _save_candidate_update(state.storage_dir, candidate, state.update_fields)
        state.active_slots.remove(slot)
    except BrainAPIError as exc:
        error_text = redact_error_message(exc)
        candidate["lifecycle_status"] = "simulation_result_failed"
        candidate = append_scientific_audit_event(
            candidate,
            operation="official_simulation_writeback",
            source="web_official_simulation_result",
            feedback_sources=["official_simulation_result"],
            official_api_called=True,
            details={"status": "RESULT_FETCH_FAILED", "simulation_id": sim_id, "error": error_text},
        )
        _clear_candidate_simulation_cooldown(candidate)
        state.failed += 1
        state.results.append({
            "alpha_id": alpha_id,
            "simulation_id": sim_id,
            "status": "result_fetch_failed",
            "error": error_text,
        })
        _append_backtest_record(state.storage_dir, {
            "action": "failed",
            "slot": i + 1,
            "alpha_id": alpha_id,
            "simulation_id": sim_id,
            "status": "RESULT_FETCH_FAILED",
            "expression": expression,
            "error": error_text,
            "poll_count": poll_attempt,
            "poll_elapsed_seconds": round(max(0.0, status_elapsed), 1),
            "next_poll_seconds": 0.0,
            "progress_percent": _progress_percent(i, state.total, status_elapsed, state.poll_timeout),
            "message": f"官方模拟结果获取失败，已等待 {status_elapsed:.1f} 秒。",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        })
        _save_candidate_update(state.storage_dir, candidate, state.update_fields)
        state.active_slots.remove(slot)


def _handle_failed_result(
    state: Any,
    slot: dict[str, Any],
    *,
    poll_attempt: int,
    status_elapsed: float,
) -> None:
    """Handle a FAILED simulation: record evidence, update state."""
    candidate = slot["candidate"]
    alpha_id = str(slot["alpha_id"])
    expression = str(slot["expression"])
    sim_id = str(slot["simulation_id"])
    i = int(slot["slot_index"])
    failure_evidence = _simulation_failure_evidence(state.api, sim_id)
    failure_error = failure_evidence.get("error", "official simulation returned FAILED")
    candidate["lifecycle_status"] = "simulation_failed"
    candidate["official_metrics"] = {}
    candidate["simulation_error"] = failure_error
    candidate["last_status"] = "FAILED"
    candidate["extra_fields"] = {
        **(candidate.get("extra_fields") if isinstance(candidate.get("extra_fields"), dict) else {}),
        "last_simulation_error": failure_error,
        "simulation_failure_evidence": failure_evidence,
    }
    candidate = append_scientific_audit_event(
        candidate,
        operation="official_simulation_writeback",
        source="web_official_simulation_failure",
        feedback_sources=["official_simulation_status", "official_simulation_result"],
        official_api_called=True,
        details={"status": "FAILED", "simulation_id": sim_id, "error": failure_error},
    )
    _clear_candidate_simulation_cooldown(candidate)
    state.failed += 1
    state.results.append({
        "alpha_id": alpha_id,
        "simulation_id": sim_id,
        "status": "failed",
        "error": failure_error,
        "failure_evidence": failure_evidence,
    })
    state.last_activity = time.monotonic()

    _append_backtest_record(state.storage_dir, {
        "action": "failed",
        "slot": i + 1,
        "alpha_id": alpha_id,
        "simulation_id": sim_id,
        "status": "FAILED",
        "expression": expression,
        "error": failure_error,
        "failure_evidence": failure_evidence,
        "poll_count": poll_attempt,
        "poll_elapsed_seconds": round(max(0.0, status_elapsed), 1),
        "next_poll_seconds": 0.0,
        "progress_percent": 100,
        "message": f"官方模拟失败，已等待 {status_elapsed:.1f} 秒：{failure_error}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    })
    _save_candidate_update(state.storage_dir, candidate, state.update_fields)
    state.active_slots.remove(slot)
