"""Polling loop for official BRAIN simulations.

Extracted from ``simulate_candidates_job`` to keep modules focused.
"""

from __future__ import annotations

import time
from typing import Any

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.web_candidates.simulation_failures import (
    append_official_simulation_audit as _append_official_simulation_audit,
)
from brain_alpha_ops.web_candidates.simulation_runtime import (
    _progress_percent,
    _update_simulation_progress,
)
from brain_alpha_ops.web_candidates.simulation_state import (
    append_backtest_record as _append_backtest_record,
    clear_candidate_simulation_cooldown as _clear_candidate_simulation_cooldown,
    save_candidate_update as _save_candidate_update,
)

from ._results import _handle_completed_result, _handle_failed_result


def _run_polling_loop(state: Any) -> None:
    """Poll active simulation slots until all complete or job is cancelled."""
    while state.active_slots:
        if state.job_store.is_cancelled(state.job_id):
            break
        time.sleep(state.poll_interval)

        for slot in list(state.active_slots):
            if state.job_store.is_cancelled(state.job_id):
                break

            i = int(slot["slot_index"])
            candidate = slot["candidate"]
            alpha_id = str(slot["alpha_id"])
            expression = str(slot["expression"])
            sim_id = str(slot["simulation_id"])
            poll_start = float(slot["poll_start"])
            submit_attempts = int(slot.get("submit_attempts") or 0)
            poll_attempt = int(slot.get("poll_attempt") or 0)

            next_poll_at = float(slot.get("next_poll_at") or 0.0)
            now = time.monotonic()
            if next_poll_at and now < next_poll_at:
                continue

            elapsed = time.monotonic() - poll_start
            stall_elapsed = time.monotonic() - state.last_activity

            if elapsed > state.poll_timeout:
                candidate["lifecycle_status"] = "simulation_poll_timeout"
                _clear_candidate_simulation_cooldown(candidate)
                state.failed += 1
                state.results.append({
                    "alpha_id": alpha_id,
                    "simulation_id": sim_id,
                    "status": "poll_timeout",
                })
                _append_backtest_record(state.storage_dir, {
                    "action": "failed",
                    "slot": i + 1,
                    "alpha_id": alpha_id,
                    "simulation_id": sim_id,
                    "status": "POLL_TIMEOUT",
                    "expression": expression,
                    "poll_count": poll_attempt,
                    "poll_elapsed_seconds": round(max(0.0, elapsed), 1),
                    "next_poll_seconds": 0.0,
                    "progress_percent": _progress_percent(i, state.total, elapsed, state.poll_timeout),
                    "message": f"官方模拟轮询超时，已等待 {elapsed:.1f} 秒。",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                })
                candidate = _append_official_simulation_audit(
                    candidate,
                    source="web_official_simulation_poll_timeout",
                    status="POLL_TIMEOUT",
                    simulation_id=sim_id,
                    poll_count=poll_attempt,
                )
                _save_candidate_update(state.storage_dir, candidate, state.terminal_audit_update_fields)
                state.active_slots.remove(slot)
                continue

            if stall_elapsed > state.stall_timeout:
                candidate["lifecycle_status"] = "simulation_stall_detected"
                _clear_candidate_simulation_cooldown(candidate)
                state.failed += 1
                state.results.append({
                    "alpha_id": alpha_id,
                    "simulation_id": sim_id,
                    "status": "stall_detected",
                })
                _append_backtest_record(state.storage_dir, {
                    "action": "failed",
                    "slot": i + 1,
                    "alpha_id": alpha_id,
                    "simulation_id": sim_id,
                    "status": "STALL_DETECTED",
                    "expression": expression,
                    "poll_count": poll_attempt,
                    "poll_elapsed_seconds": round(max(0.0, elapsed), 1),
                    "next_poll_seconds": 0.0,
                    "progress_percent": _progress_percent(i, state.total, elapsed, state.poll_timeout),
                    "message": f"官方模拟轮询停滞，已等待 {elapsed:.1f} 秒。",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                })
                candidate = _append_official_simulation_audit(
                    candidate,
                    source="web_official_simulation_stall_detected",
                    status="STALL_DETECTED",
                    simulation_id=sim_id,
                    poll_count=poll_attempt,
                )
                _save_candidate_update(state.storage_dir, candidate, state.terminal_audit_update_fields)
                state.active_slots.remove(slot)
                continue

            poll_attempt += 1
            slot["poll_attempt"] = poll_attempt
            polling_message = (
                f"正在等待官方模拟结果 {i+1}/{state.total}，已轮询 {poll_attempt} 次，"
                f"已等待 {elapsed:.1f} 秒。"
            )
            _update_simulation_progress(
                state.job_store,
                state.job_id,
                phase="simulation_polling",
                message=polling_message,
                slot_index=i,
                total=state.total,
                completed=state.completed,
                failed=state.failed,
                alpha_id=alpha_id,
                simulation_id=sim_id,
                poll_attempt=poll_attempt,
                poll_elapsed=elapsed,
                poll_timeout=state.poll_timeout,
                last_status="RUNNING",
                submit_attempts=submit_attempts,
            )

            try:
                status = state.api.poll_simulation(sim_id)
            except BrainAPIError as exc:
                if exc.status_code == 429:
                    wait = float(exc.retry_after or state.poll_interval * 2)
                    rate_elapsed = time.monotonic() - poll_start
                    rate_wait = min(wait, 30.0)
                    rate_message = (
                        f"官方模拟轮询被限流，已等待 {rate_elapsed:.1f} 秒；"
                        f"{rate_wait:.0f} 秒后继续。"
                    )
                    _update_simulation_progress(
                        state.job_store,
                        state.job_id,
                        phase="simulation_rate_limited",
                        message=rate_message,
                        slot_index=i,
                        total=state.total,
                        completed=state.completed,
                        failed=state.failed,
                        alpha_id=alpha_id,
                        simulation_id=sim_id,
                        poll_attempt=poll_attempt,
                        poll_elapsed=rate_elapsed,
                        poll_timeout=state.poll_timeout,
                        last_status="RATE_LIMITED",
                        submit_attempts=submit_attempts,
                    )
                    _append_backtest_record(state.storage_dir, {
                        "action": "polling",
                        "slot": i + 1,
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "RATE_LIMITED",
                        "expression": expression,
                        "poll_count": poll_attempt,
                        "poll_elapsed_seconds": round(max(0.0, rate_elapsed), 1),
                        "next_poll_seconds": rate_wait,
                        "progress_percent": _progress_percent(i, state.total, rate_elapsed, state.poll_timeout),
                        "message": rate_message,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    })
                    slot["next_poll_at"] = time.monotonic() + rate_wait
                    continue
                state.log.warning("Poll error for %s: %s", redact_text(alpha_id), redact_error_message(exc))
                error_elapsed = time.monotonic() - poll_start
                error_message = f"官方模拟轮询暂时失败，已等待 {error_elapsed:.1f} 秒，系统将继续重试: {redact_error_message(exc)}"
                _update_simulation_progress(
                    state.job_store,
                    state.job_id,
                    phase="simulation_poll_error",
                    message=error_message,
                    slot_index=i,
                    total=state.total,
                    completed=state.completed,
                    failed=state.failed,
                    alpha_id=alpha_id,
                    simulation_id=sim_id,
                    poll_attempt=poll_attempt,
                    poll_elapsed=error_elapsed,
                    poll_timeout=state.poll_timeout,
                    last_status="POLL_ERROR",
                    submit_attempts=submit_attempts,
                )
                _append_backtest_record(state.storage_dir, {
                    "action": "poll_error",
                    "slot": i + 1,
                    "alpha_id": alpha_id,
                    "simulation_id": sim_id,
                    "status": "POLL_ERROR",
                    "expression": expression,
                    "error": redact_error_message(exc),
                    "poll_count": poll_attempt,
                    "poll_elapsed_seconds": round(max(0.0, error_elapsed), 1),
                    "next_poll_seconds": state.poll_interval,
                    "progress_percent": _progress_percent(i, state.total, error_elapsed, state.poll_timeout),
                    "message": error_message,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                })
                continue

            state.last_activity = time.monotonic()
            slot.pop("next_poll_at", None)
            status_elapsed = time.monotonic() - poll_start
            status_message = f"官方模拟状态 {status}，继续等待结果 {i+1}/{state.total}，已等待 {status_elapsed:.1f} 秒。"
            _update_simulation_progress(
                state.job_store,
                state.job_id,
                phase="simulation_polling",
                message=status_message,
                slot_index=i,
                total=state.total,
                completed=state.completed,
                failed=state.failed,
                alpha_id=alpha_id,
                simulation_id=sim_id,
                poll_attempt=poll_attempt,
                poll_elapsed=status_elapsed,
                poll_timeout=state.poll_timeout,
                last_status=status,
                submit_attempts=submit_attempts,
            )

            if status == "COMPLETED":
                _handle_completed_result(state, slot, poll_attempt=poll_attempt, status_elapsed=status_elapsed)
                continue

            elif status == "FAILED":
                _handle_failed_result(state, slot, poll_attempt=poll_attempt, status_elapsed=status_elapsed)
                continue

            # Still running, update progress
            candidate["lifecycle_status"] = "simulation_running"
            _append_backtest_record(state.storage_dir, {
                "action": "polling",
                "slot": i + 1,
                "alpha_id": alpha_id,
                "simulation_id": sim_id,
                "status": status,
                "expression": expression,
                "poll_count": poll_attempt,
                "poll_elapsed_seconds": round(max(0.0, status_elapsed), 1),
                "next_poll_seconds": state.poll_interval,
                "progress_percent": _progress_percent(i, state.total, status_elapsed, state.poll_timeout),
                "message": status_message,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            })
            _save_candidate_update(state.storage_dir, candidate, state.update_fields)
