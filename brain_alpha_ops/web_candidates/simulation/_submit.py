"""Submission loop for official BRAIN simulations.

Extracted from ``simulate_candidates_job`` to keep modules focused.
"""

from __future__ import annotations

import time
from typing import Any

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.web_candidates.audit import append_scientific_audit_event
from brain_alpha_ops.web_candidates.simulation_failures import (
    append_official_simulation_audit as _append_official_simulation_audit,
)
from brain_alpha_ops.web_candidates.simulation_runtime import (
    _progress_percent,
    _simulation_retry_pause_seconds,
    _update_simulation_progress,
)
from brain_alpha_ops.web_candidates.simulation_state import (
    append_backtest_record as _append_backtest_record,
    clear_account_simulation_cooldown as _clear_account_simulation_cooldown,
    clear_candidate_simulation_cooldown as _clear_candidate_simulation_cooldown,
    defer_candidate as _defer_candidate,
    record_account_simulation_cooldown as _record_account_simulation_cooldown,
    save_candidate_update as _save_candidate_update,
)


def _run_submission_loop(state: Any, targets: list[dict[str, Any]]) -> None:
    """Submit eligible candidates to the BRAIN API with retry handling."""
    for i, candidate in enumerate(targets):
        if state.job_store.is_cancelled(state.job_id):
            state.log.info("Simulation job %s cancelled", state.job_id)
            break

        alpha_id = candidate.get("alpha_id", "")
        expression = candidate.get("expression", "")
        ds = candidate.get("dataset_id") or state.settings.get("dataset", "")
        sim_settings = dict(state.settings)
        if ds:
            sim_settings["dataset"] = ds

        state.job_store.update(state.job_id, progress={
            "phase": "simulating",
            "message": f"正在模拟候选 {i+1}/{state.total}: {alpha_id}",
            "percent": int(i / state.total * 90),
            "data": {
                "total": state.total,
                "completed": state.completed,
                "failed": state.failed,
                "current_alpha_id": alpha_id,
            },
        })

        sim_id = ""
        submit_started = time.monotonic()
        submit_attempts = 0
        while True:
            if state.job_store.is_cancelled(state.job_id):
                break

            submit_elapsed = time.monotonic() - submit_started
            submit_attempts += 1
            _update_simulation_progress(
                state.job_store,
                state.job_id,
                phase="simulation_submitting",
                message=f"正在提交候选 {i+1}/{state.total} 的官方模拟，第 {submit_attempts} 次尝试，已等待 {submit_elapsed:.1f} 秒。",
                slot_index=i,
                total=state.total,
                completed=state.completed,
                failed=state.failed,
                alpha_id=alpha_id,
                poll_elapsed=submit_elapsed,
                poll_timeout=state.poll_timeout,
                last_status="SUBMITTING",
                submit_attempts=submit_attempts,
            )

            try:
                sim_id = state.api.submit_simulation(expression, sim_settings)
            except BrainAPIError as exc:
                error_text = redact_error_message(exc)
                if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in error_text:
                    retry_seconds = _simulation_retry_pause_seconds(state.config, exc)
                    _defer_candidate(
                        candidate,
                        lifecycle_status="simulation_deferred_concurrency_limit",
                        error_text=error_text,
                        retry_seconds=retry_seconds,
                    )
                    _record_account_simulation_cooldown(
                        state.storage_dir,
                        lifecycle_status="simulation_deferred_concurrency_limit",
                        error_text=error_text,
                        retry_seconds=retry_seconds,
                    )
                    wait_elapsed = time.monotonic() - submit_started
                    if wait_elapsed >= state.poll_timeout:
                        capacity_message = (
                            f"官方模拟并发槽位持续占满，候选 {i+1}/{state.total} 已等待 {wait_elapsed:.1f} 秒；"
                            "已按冷却延后，请稍后重试。"
                        )
                        state.failed += 1
                        state.results.append({
                            "alpha_id": alpha_id,
                            "status": "deferred_concurrency_limit",
                            "error": error_text,
                            "retry_after_seconds": retry_seconds,
                        })
                        _append_backtest_record(state.storage_dir, {
                            "action": "capacity_timeout",
                            "slot": i + 1,
                            "alpha_id": alpha_id,
                            "status": "CAPACITY_TIMEOUT",
                            "expression": expression,
                            "error": error_text,
                            "retry_after_seconds": retry_seconds,
                            "submit_attempts": submit_attempts,
                            "poll_elapsed_seconds": round(max(0.0, wait_elapsed), 1),
                            "next_poll_seconds": 0.0,
                            "progress_percent": _progress_percent(i, state.total, wait_elapsed, state.poll_timeout),
                            "message": capacity_message,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                        })
                        _update_simulation_progress(
                            state.job_store,
                            state.job_id,
                            phase="simulation_capacity_timeout",
                            message=capacity_message,
                            slot_index=i,
                            total=state.total,
                            completed=state.completed,
                            failed=state.failed,
                            alpha_id=alpha_id,
                            poll_elapsed=wait_elapsed,
                            poll_timeout=state.poll_timeout,
                            last_status="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
                            submit_attempts=submit_attempts,
                        )
                        candidate = _append_official_simulation_audit(
                            candidate,
                            source="web_official_simulation_capacity_timeout",
                            status="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
                            error=error_text,
                            retry_after_seconds=retry_seconds,
                            submit_attempts=submit_attempts,
                        )
                        _save_candidate_update(state.storage_dir, candidate, state.cooldown_audit_update_fields)
                        state.stop_new_submissions = True
                        break
                    capacity_message = (
                        f"官方模拟并发槽位已满，候选 {i+1}/{state.total} 已等待 {wait_elapsed:.1f} 秒；"
                        f"{state.poll_interval:.0f} 秒后自动重试。"
                    )
                    _append_backtest_record(state.storage_dir, {
                        "action": "capacity_wait",
                        "slot": i + 1,
                        "alpha_id": alpha_id,
                        "status": "CAPACITY_WAIT",
                        "expression": expression,
                        "error": error_text,
                        "retry_after_seconds": retry_seconds,
                        "submit_attempts": submit_attempts,
                        "poll_elapsed_seconds": round(max(0.0, wait_elapsed), 1),
                        "next_poll_seconds": state.poll_interval,
                        "progress_percent": _progress_percent(i, state.total, wait_elapsed, state.poll_timeout),
                        "message": capacity_message,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    })
                    state.log.warning(
                        "Concurrent simulation limit hit for %s; retrying in %.1fs",
                        redact_text(alpha_id),
                        state.poll_interval,
                    )
                    _update_simulation_progress(
                        state.job_store,
                        state.job_id,
                        phase="simulation_capacity_wait",
                        message=capacity_message,
                        slot_index=i,
                        total=state.total,
                        completed=state.completed,
                        failed=state.failed,
                        alpha_id=alpha_id,
                        poll_elapsed=wait_elapsed,
                        poll_timeout=state.poll_timeout,
                        last_status="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
                        submit_attempts=submit_attempts,
                    )
                    candidate = _append_official_simulation_audit(
                        candidate,
                        source="web_official_simulation_capacity_wait",
                        status="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
                        error=error_text,
                        retry_after_seconds=retry_seconds,
                        submit_attempts=submit_attempts,
                    )
                    _save_candidate_update(state.storage_dir, candidate, state.cooldown_audit_update_fields)
                    if state.active_slots:
                        state.failed += 1
                        state.results.append({
                            "alpha_id": alpha_id,
                            "status": "deferred_concurrency_limit",
                            "error": error_text,
                            "retry_after_seconds": retry_seconds,
                        })
                        candidate = _append_official_simulation_audit(
                            candidate,
                            source="web_official_simulation_capacity_deferred",
                            status="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
                            error=error_text,
                            retry_after_seconds=retry_seconds,
                            submit_attempts=submit_attempts,
                        )
                        _save_candidate_update(state.storage_dir, candidate, state.cooldown_audit_update_fields)
                        state.stop_new_submissions = True
                        break
                    time.sleep(state.poll_interval)
                    continue
                if exc.status_code == 429:
                    retry_seconds = _simulation_retry_pause_seconds(state.config, exc)
                    _defer_candidate(
                        candidate,
                        lifecycle_status="simulation_deferred_rate_limit",
                        error_text=error_text,
                        retry_seconds=retry_seconds,
                    )
                    _record_account_simulation_cooldown(
                        state.storage_dir,
                        lifecycle_status="simulation_deferred_rate_limit",
                        error_text=error_text,
                        retry_seconds=retry_seconds,
                    )
                    state.log.warning("Rate limit hit for %s, stopping", redact_text(alpha_id))
                    state.failed += 1
                    state.results.append({
                        "alpha_id": alpha_id,
                        "status": "deferred_rate_limit",
                        "error": error_text,
                        "retry_after_seconds": retry_seconds,
                    })
                    candidate = _append_official_simulation_audit(
                        candidate,
                        source="web_official_simulation_rate_limit",
                        status="RATE_LIMITED",
                        error=error_text,
                        retry_after_seconds=retry_seconds,
                        submit_attempts=submit_attempts,
                    )
                    _save_candidate_update(state.storage_dir, candidate, state.cooldown_audit_update_fields)
                    state.stop_new_submissions = True
                    break
                candidate["lifecycle_status"] = "simulation_submit_failed"
                _clear_candidate_simulation_cooldown(candidate)
                state.failed += 1
                state.results.append({
                    "alpha_id": alpha_id,
                    "status": "submit_failed",
                    "error": error_text,
                })
                candidate = _append_official_simulation_audit(
                    candidate,
                    source="web_official_simulation_submit_failed",
                    status="SUBMIT_FAILED",
                    error=error_text,
                    submit_attempts=submit_attempts,
                )
                _save_candidate_update(state.storage_dir, candidate, state.terminal_audit_update_fields)
                break

            candidate["simulation_id"] = sim_id
            candidate["lifecycle_status"] = "simulation_submitted"
            candidate = append_scientific_audit_event(
                candidate,
                operation="official_simulation_writeback",
                source="web_official_simulation_submit",
                feedback_sources=["official_simulation_status"],
                official_api_called=True,
                details={"status": "SUBMITTED", "simulation_id": sim_id},
            )
            slot_candidate = candidate
            _clear_candidate_simulation_cooldown(candidate)
            _clear_account_simulation_cooldown(state.storage_dir)
            state.last_activity = time.monotonic()
            _update_simulation_progress(
                state.job_store,
                state.job_id,
                phase="simulation_submitted",
                message=f"候选 {i+1}/{state.total} 已提交官方模拟，正在等待 BRAIN 返回状态，已等待 0.0 秒。",
                slot_index=i,
                total=state.total,
                completed=state.completed,
                failed=state.failed,
                alpha_id=alpha_id,
                simulation_id=sim_id,
                poll_timeout=state.poll_timeout,
                submit_attempts=submit_attempts,
            )

            _append_backtest_record(state.storage_dir, {
                "action": "submitted",
                "slot": i + 1,
                "alpha_id": alpha_id,
                "simulation_id": sim_id,
                "status": "SUBMITTED",
                "expression": expression,
                "poll_count": 0,
                "poll_elapsed_seconds": 0.0,
                "next_poll_seconds": state.poll_interval,
                "progress_percent": _progress_percent(i, state.total, 0.0, state.poll_timeout),
                "message": f"候选 {i+1}/{state.total} 已提交官方模拟，正在等待 BRAIN 返回状态，已等待 0.0 秒。",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            })
            _save_candidate_update(state.storage_dir, candidate, state.update_fields)
            state.active_slots.append({
                "slot_index": i,
                "candidate": slot_candidate,
                "alpha_id": alpha_id,
                "expression": expression,
                "simulation_id": sim_id,
                "poll_start": time.monotonic(),
                "poll_attempt": 0,
                "submit_attempts": submit_attempts,
            })
            break

        if state.job_store.is_cancelled(state.job_id) or state.stop_new_submissions:
            break
