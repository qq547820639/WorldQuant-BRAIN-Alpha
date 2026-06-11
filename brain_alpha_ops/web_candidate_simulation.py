"""Per-candidate BRAIN API simulation service for the web console.

Provides a background-job endpoint that takes locally-generated candidates,
submits them to the BRAIN API for official simulation, polls for results,
and updates candidates with official_metrics so the scoring and gate
systems can evaluate them.

Key design constraints:
  - Respects BRAIN API rate limits (CONCURRENT_SIMULATION_LIMIT_EXCEEDED)
  - Uses stall detection: auto-interrupts if no progress for N seconds
  - Writes results back to candidates.jsonl so the UI stays in sync
  - Official thresholds/config stay sourced from run_config; the Web task
    heartbeat cadence is fixed at 5 seconds so operators see predictable
    elapsed-wait progress.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.web_candidate_simulation_runtime import (
    _create_api,
    _progress_percent,
    _resolve_credentials,
    _simulation_poll_interval,
    _simulation_poll_timeout,
    _simulation_retry_pause_seconds,
    _update_simulation_progress,
    _web_backtest_refresh_interval,
)
from brain_alpha_ops.web_candidate_simulation_state import (
    COOLDOWN_UPDATE_FIELDS,
    active_account_simulation_cooldown as _active_account_simulation_cooldown,
    append_backtest_record as _append_backtest_record,
    candidate_score as _candidate_score,
    clear_account_simulation_cooldown as _clear_account_simulation_cooldown,
    clear_candidate_simulation_cooldown as _clear_candidate_simulation_cooldown,
    dedupe_simulation_targets as _dedupe_simulation_targets,
    default_simulation_dataset as _default_simulation_dataset,
    defer_candidate as _defer_candidate,
    eligible_for_simulation as _eligible_for_simulation,
    load_candidates as _load_candidates,
    record_account_simulation_cooldown as _record_account_simulation_cooldown,
    save_candidate_update as _save_candidate_update,
    save_candidates as _save_candidates,
    score_simulated_candidate as _score_simulated_candidate,
    simulation_target_key as _simulation_target_key,
)

logger = logging.getLogger(__name__)

# Stall detection: if no simulation completes within this window, auto-cancel
_DEFAULT_STALL_TIMEOUT_SECONDS = 180.0
# Minimum prior score to be eligible for simulation
_DEFAULT_MIN_SCORE = 60.0
_SIMULATION_FAILURE_KEYS = (
    "error",
    "detail",
    "message",
    "reason",
    "failureReason",
    "failure_reason",
    "status",
    "state",
)


def simulate_candidates_job(
    job_id: str,
    payload: dict[str, Any],
    *,
    job_store: Any,
    log: logging.Logger = logger,
) -> None:
    """Background job: submit eligible candidates for BRAIN simulation.

    This is the core function that bridges locally-generated candidates
    to official BRAIN metrics. It:
      1. Loads candidates from candidates.jsonl
      2. Filters to eligible candidates (score >= threshold, no existing metrics)
      3. Submits each to BRAIN API for simulation (one at a time)
      4. Polls for results with stall detection
      5. Updates candidates with official_metrics and re-scores
      6. Writes results back to candidates.jsonl
    """
    try:
        config = load_run_config()
        storage_dir = config.ops.storage_dir
        budget = config.ops.budget

        # Resolve parameters
        min_score = float(payload.get("min_score", budget.min_prior_score_for_official_simulation))
        max_simulations = int(payload.get("max_simulations", budget.max_official_simulations_per_cycle))
        poll_timeout = _simulation_poll_timeout(config, payload)
        stall_timeout = float(payload.get("stall_timeout", _DEFAULT_STALL_TIMEOUT_SECONDS))
        poll_interval = _web_backtest_refresh_interval(payload)
        candidate_ids = payload.get("candidate_ids")  # Optional: specific IDs to simulate

        # Load and filter candidates
        candidates = _load_candidates(storage_dir)
        if not candidates:
            job_store.update(job_id, status="completed", progress={
                "phase": "no_candidates",
                "message": "没有找到候选Alpha。",
                "percent": 100,
            })
            return

        account_cooldown = _active_account_simulation_cooldown(storage_dir)
        if account_cooldown:
            remaining = float(account_cooldown.get("remaining_seconds", 0.0) or 0.0)
            job_store.update(job_id, status="completed", progress={
                "phase": "simulation_account_cooldown",
                "message": f"官方模拟仍在账号级冷却中，请约 {remaining:.0f} 秒后再试。",
                "percent": 100,
                "data": {
                    "total_candidates": len(candidates),
                    "eligible": 0,
                    "account_cooldown": account_cooldown,
                },
            })
            return

        if candidate_ids:
            requested_ids = {str(candidate_id).strip() for candidate_id in candidate_ids if str(candidate_id).strip()}
            targets = [
                c for c in candidates
                if _candidate_matches_requested_ids(c, requested_ids) and _eligible_for_simulation(c, min_score)
            ]
        else:
            targets = [c for c in candidates if _eligible_for_simulation(c, min_score)]

        if not targets:
            job_store.update(job_id, status="completed", progress={
                "phase": "no_eligible",
                "message": f"没有符合条件的候选Alpha (最低分数: {min_score})。",
                "percent": 100,
                "data": {"total_candidates": len(candidates), "eligible": 0},
            })
            return

        default_dataset = _default_simulation_dataset(config)
        targets = _dedupe_simulation_targets(targets, default_dataset=default_dataset)[:max_simulations]

        # Create BRAIN API client with session credentials from payload
        try:
            api = _create_api(
                config,
                username=str(payload.get("username", "")),
                password=str(payload.get("password", "")),
                token=str(payload.get("token", "")),
            )
            # Authenticate before any simulation calls
            auth_result = api.authenticate()
            log.info("BRAIN API authenticated: %s", auth_result.get("auth", auth_result.get("environment", "unknown")))
        except Exception as exc:
            msg = redact_error_message(exc)
            log.error("Failed to create BRAIN API client: %s", msg)
            job_store.update(job_id, status="failed", error=msg, progress={
                "phase": "api_init_failed",
                "message": f"BRAIN API 客户端初始化失败: {msg}",
                "percent": 0,
            })
            return

        # Settings for simulation
        settings = config.ops.settings.to_platform_dict()["settings"]

        # Track progress
        total = len(targets)
        completed = 0
        failed = 0
        last_activity = time.monotonic()
        results: list[dict[str, Any]] = []

        job_store.update(job_id, status="running", progress={
            "phase": "simulating",
            "message": f"开始模拟 {total} 个候选Alpha...",
            "percent": 0,
            "data": {"total": total, "completed": 0, "failed": 0},
        })

        for i, candidate in enumerate(targets):
            # Check for cancellation
            if job_store.is_cancelled(job_id):
                log.info("Simulation job %s cancelled", job_id)
                break

            alpha_id = candidate.get("alpha_id", "")
            expression = candidate.get("expression", "")
            ds = candidate.get("dataset_id") or settings.get("dataset", "")
            sim_settings = dict(settings)
            if ds:
                sim_settings["dataset"] = ds

            job_store.update(job_id, progress={
                "phase": "simulating",
                "message": f"正在模拟候选 {i+1}/{total}: {alpha_id}",
                "percent": int(i / total * 90),
                "data": {
                    "total": total,
                    "completed": completed,
                    "failed": failed,
                    "current_alpha_id": alpha_id,
                },
            })

            # Submit simulation. Official capacity errors are retried on the
            # Web heartbeat cadence, but the submit phase must still be bounded:
            # otherwise account-level capacity can leave the browser in an
            # unclear "running" state indefinitely.
            sim_id = ""
            submit_started = time.monotonic()
            submit_attempts = 0
            while True:
                if job_store.is_cancelled(job_id):
                    break

                submit_elapsed = time.monotonic() - submit_started
                submit_attempts += 1
                _update_simulation_progress(
                    job_store,
                    job_id,
                    phase="simulation_submitting",
                    message=f"正在提交候选 {i+1}/{total} 的官方模拟，第 {submit_attempts} 次尝试，已等待 {submit_elapsed:.1f} 秒。",
                    slot_index=i,
                    total=total,
                    completed=completed,
                    failed=failed,
                    alpha_id=alpha_id,
                    poll_elapsed=submit_elapsed,
                    poll_timeout=poll_timeout,
                    last_status="SUBMITTING",
                    submit_attempts=submit_attempts,
                )

                try:
                    sim_id = api.submit_simulation(expression, sim_settings)
                except BrainAPIError as exc:
                    error_text = redact_error_message(exc)
                    if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in error_text:
                        retry_seconds = _simulation_retry_pause_seconds(config, exc)
                        _defer_candidate(
                            candidate,
                            lifecycle_status="simulation_deferred_concurrency_limit",
                            error_text=error_text,
                            retry_seconds=retry_seconds,
                        )
                        _record_account_simulation_cooldown(
                            storage_dir,
                            lifecycle_status="simulation_deferred_concurrency_limit",
                            error_text=error_text,
                            retry_seconds=retry_seconds,
                        )
                        wait_elapsed = time.monotonic() - submit_started
                        if wait_elapsed >= poll_timeout:
                            capacity_message = (
                                f"官方模拟并发槽位持续占满，候选 {i+1}/{total} 已等待 {wait_elapsed:.1f} 秒；"
                                "已按冷却延后，请稍后重试。"
                            )
                            failed += 1
                            results.append({
                                "alpha_id": alpha_id,
                                "status": "deferred_concurrency_limit",
                                "error": error_text,
                                "retry_after_seconds": retry_seconds,
                            })
                            _append_backtest_record(storage_dir, {
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
                                "progress_percent": _progress_percent(i, total, wait_elapsed, poll_timeout),
                                "message": capacity_message,
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                            })
                            _update_simulation_progress(
                                job_store,
                                job_id,
                                phase="simulation_capacity_timeout",
                                message=capacity_message,
                                slot_index=i,
                                total=total,
                                completed=completed,
                                failed=failed,
                                alpha_id=alpha_id,
                                poll_elapsed=wait_elapsed,
                                poll_timeout=poll_timeout,
                                last_status="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
                                submit_attempts=submit_attempts,
                            )
                            _save_candidate_update(storage_dir, candidate, COOLDOWN_UPDATE_FIELDS)
                            break
                        capacity_message = (
                            f"官方模拟并发槽位已满，候选 {i+1}/{total} 已等待 {wait_elapsed:.1f} 秒；"
                            f"{poll_interval:.0f} 秒后自动重试。"
                        )
                        _append_backtest_record(storage_dir, {
                            "action": "capacity_wait",
                            "slot": i + 1,
                            "alpha_id": alpha_id,
                            "status": "CAPACITY_WAIT",
                            "expression": expression,
                            "error": error_text,
                            "retry_after_seconds": retry_seconds,
                            "submit_attempts": submit_attempts,
                            "poll_elapsed_seconds": round(max(0.0, wait_elapsed), 1),
                            "next_poll_seconds": poll_interval,
                            "progress_percent": _progress_percent(i, total, wait_elapsed, poll_timeout),
                            "message": capacity_message,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                        })
                        log.warning(
                            "Concurrent simulation limit hit for %s; retrying in %.1fs",
                            redact_text(alpha_id),
                            poll_interval,
                        )
                        _update_simulation_progress(
                            job_store,
                            job_id,
                            phase="simulation_capacity_wait",
                            message=capacity_message,
                            slot_index=i,
                            total=total,
                            completed=completed,
                            failed=failed,
                            alpha_id=alpha_id,
                            poll_elapsed=wait_elapsed,
                            poll_timeout=poll_timeout,
                            last_status="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
                            submit_attempts=submit_attempts,
                        )
                        _save_candidate_update(storage_dir, candidate, COOLDOWN_UPDATE_FIELDS)
                        time.sleep(poll_interval)
                        continue
                    if exc.status_code == 429:
                        retry_seconds = _simulation_retry_pause_seconds(config, exc)
                        _defer_candidate(
                            candidate,
                            lifecycle_status="simulation_deferred_rate_limit",
                            error_text=error_text,
                            retry_seconds=retry_seconds,
                        )
                        _record_account_simulation_cooldown(
                            storage_dir,
                            lifecycle_status="simulation_deferred_rate_limit",
                            error_text=error_text,
                            retry_seconds=retry_seconds,
                        )
                        log.warning("Rate limit hit for %s, stopping", redact_text(alpha_id))
                        failed += 1
                        results.append({
                            "alpha_id": alpha_id,
                            "status": "deferred_rate_limit",
                            "error": error_text,
                            "retry_after_seconds": retry_seconds,
                        })
                        _save_candidate_update(storage_dir, candidate, COOLDOWN_UPDATE_FIELDS)
                        break
                    candidate["lifecycle_status"] = "simulation_submit_failed"
                    _clear_candidate_simulation_cooldown(candidate)
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "status": "submit_failed",
                        "error": error_text,
                    })
                    _save_candidate_update(storage_dir, candidate, COOLDOWN_UPDATE_FIELDS)
                    break

                candidate["simulation_id"] = sim_id
                candidate["lifecycle_status"] = "simulation_submitted"
                _clear_candidate_simulation_cooldown(candidate)
                _clear_account_simulation_cooldown(storage_dir)
                last_activity = time.monotonic()
                _update_simulation_progress(
                    job_store,
                    job_id,
                    phase="simulation_submitted",
                    message=f"候选 {i+1}/{total} 已提交官方模拟，正在等待 BRAIN 返回状态，已等待 0.0 秒。",
                    slot_index=i,
                    total=total,
                    completed=completed,
                    failed=failed,
                    alpha_id=alpha_id,
                    simulation_id=sim_id,
                    poll_timeout=poll_timeout,
                    submit_attempts=submit_attempts,
                )

                _append_backtest_record(storage_dir, {
                    "action": "submitted",
                    "slot": i + 1,
                    "alpha_id": alpha_id,
                    "simulation_id": sim_id,
                    "status": "SUBMITTED",
                    "expression": expression,
                    "poll_count": 0,
                    "poll_elapsed_seconds": 0.0,
                    "next_poll_seconds": poll_interval,
                    "progress_percent": _progress_percent(i, total, 0.0, poll_timeout),
                    "message": f"候选 {i+1}/{total} 已提交官方模拟，正在等待 BRAIN 返回状态，已等待 0.0 秒。",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                })
                break

            if job_store.is_cancelled(job_id):
                break
            if not sim_id:
                break

            # Poll for result
            poll_start = time.monotonic()
            poll_attempt = 0
            while True:
                if job_store.is_cancelled(job_id):
                    break

                elapsed = time.monotonic() - poll_start
                stall_elapsed = time.monotonic() - last_activity

                if elapsed > poll_timeout:
                    candidate["lifecycle_status"] = "simulation_poll_timeout"
                    _clear_candidate_simulation_cooldown(candidate)
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "poll_timeout",
                    })
                    _append_backtest_record(storage_dir, {
                        "action": "failed",
                        "slot": i + 1,
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "POLL_TIMEOUT",
                        "expression": expression,
                        "poll_count": poll_attempt,
                        "poll_elapsed_seconds": round(max(0.0, elapsed), 1),
                        "next_poll_seconds": 0.0,
                        "progress_percent": _progress_percent(i, total, elapsed, poll_timeout),
                        "message": f"官方模拟轮询超时，已等待 {elapsed:.1f} 秒。",
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    })
                    break

                if stall_elapsed > stall_timeout:
                    candidate["lifecycle_status"] = "simulation_stall_detected"
                    _clear_candidate_simulation_cooldown(candidate)
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "stall_detected",
                    })
                    _append_backtest_record(storage_dir, {
                        "action": "failed",
                        "slot": i + 1,
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "STALL_DETECTED",
                        "expression": expression,
                        "poll_count": poll_attempt,
                        "poll_elapsed_seconds": round(max(0.0, elapsed), 1),
                        "next_poll_seconds": 0.0,
                        "progress_percent": _progress_percent(i, total, elapsed, poll_timeout),
                        "message": f"官方模拟轮询停滞，已等待 {elapsed:.1f} 秒。",
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    })
                    break

                poll_attempt += 1
                polling_message = (
                    f"正在等待官方模拟结果 {i+1}/{total}，已轮询 {poll_attempt} 次，"
                    f"已等待 {elapsed:.1f} 秒。"
                )
                _update_simulation_progress(
                    job_store,
                    job_id,
                    phase="simulation_polling",
                    message=polling_message,
                    slot_index=i,
                    total=total,
                    completed=completed,
                    failed=failed,
                    alpha_id=alpha_id,
                    simulation_id=sim_id,
                    poll_attempt=poll_attempt,
                    poll_elapsed=elapsed,
                    poll_timeout=poll_timeout,
                    last_status="RUNNING",
                    submit_attempts=submit_attempts,
                )
                time.sleep(poll_interval)

                try:
                    status = api.poll_simulation(sim_id)
                except BrainAPIError as exc:
                    if exc.status_code == 429:
                        wait = float(exc.retry_after or poll_interval * 2)
                        rate_elapsed = time.monotonic() - poll_start
                        rate_wait = min(wait, 30.0)
                        rate_message = (
                            f"官方模拟轮询被限流，已等待 {rate_elapsed:.1f} 秒；"
                            f"{rate_wait:.0f} 秒后继续。"
                        )
                        _update_simulation_progress(
                            job_store,
                            job_id,
                            phase="simulation_rate_limited",
                            message=rate_message,
                            slot_index=i,
                            total=total,
                            completed=completed,
                            failed=failed,
                            alpha_id=alpha_id,
                            simulation_id=sim_id,
                            poll_attempt=poll_attempt,
                            poll_elapsed=rate_elapsed,
                            poll_timeout=poll_timeout,
                            last_status="RATE_LIMITED",
                            submit_attempts=submit_attempts,
                        )
                        _append_backtest_record(storage_dir, {
                            "action": "polling",
                            "slot": i + 1,
                            "alpha_id": alpha_id,
                            "simulation_id": sim_id,
                            "status": "RATE_LIMITED",
                            "expression": expression,
                            "poll_count": poll_attempt,
                            "poll_elapsed_seconds": round(max(0.0, rate_elapsed), 1),
                            "next_poll_seconds": rate_wait,
                            "progress_percent": _progress_percent(i, total, rate_elapsed, poll_timeout),
                            "message": rate_message,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                        })
                        time.sleep(rate_wait)
                        continue
                    log.warning("Poll error for %s: %s", redact_text(alpha_id), redact_error_message(exc))
                    error_elapsed = time.monotonic() - poll_start
                    error_message = f"官方模拟轮询暂时失败，已等待 {error_elapsed:.1f} 秒，系统将继续重试: {redact_error_message(exc)}"
                    _update_simulation_progress(
                        job_store,
                        job_id,
                        phase="simulation_poll_error",
                        message=error_message,
                        slot_index=i,
                        total=total,
                        completed=completed,
                        failed=failed,
                        alpha_id=alpha_id,
                        simulation_id=sim_id,
                        poll_attempt=poll_attempt,
                        poll_elapsed=error_elapsed,
                        poll_timeout=poll_timeout,
                        last_status="POLL_ERROR",
                        submit_attempts=submit_attempts,
                    )
                    _append_backtest_record(storage_dir, {
                        "action": "poll_error",
                        "slot": i + 1,
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "POLL_ERROR",
                        "expression": expression,
                        "error": redact_error_message(exc),
                        "poll_count": poll_attempt,
                        "poll_elapsed_seconds": round(max(0.0, error_elapsed), 1),
                        "next_poll_seconds": poll_interval,
                        "progress_percent": _progress_percent(i, total, error_elapsed, poll_timeout),
                        "message": error_message,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    })
                    continue

                last_activity = time.monotonic()
                status_elapsed = time.monotonic() - poll_start
                status_message = f"官方模拟状态 {status}，继续等待结果 {i+1}/{total}，已等待 {status_elapsed:.1f} 秒。"
                _update_simulation_progress(
                    job_store,
                    job_id,
                    phase="simulation_polling",
                    message=status_message,
                    slot_index=i,
                    total=total,
                    completed=completed,
                    failed=failed,
                    alpha_id=alpha_id,
                    simulation_id=sim_id,
                    poll_attempt=poll_attempt,
                    poll_elapsed=status_elapsed,
                    poll_timeout=poll_timeout,
                    last_status=status,
                    submit_attempts=submit_attempts,
                )

                if status == "COMPLETED":
                    # Fetch result
                    try:
                        result = api.fetch_result(sim_id)
                        candidate["official_alpha_id"] = result.get("alpha_id", "") or result.get("metrics", {}).get("official_alpha_id", "")
                        candidate["official_metrics"] = result.get("metrics", {})
                        candidate["lifecycle_status"] = "official_simulated"
                        _clear_candidate_simulation_cooldown(candidate)
                        last_activity = time.monotonic()

                        # Re-score with official metrics
                        try:
                            rescored = _score_simulated_candidate(candidate, config)
                            candidate.clear()
                            candidate.update(rescored)
                        except Exception as score_exc:
                            log.warning("Re-scoring failed for %s: %s", redact_text(alpha_id), redact_error_message(score_exc))

                        completed += 1
                        results.append({
                            "alpha_id": alpha_id,
                            "official_alpha_id": candidate.get("official_alpha_id", ""),
                            "simulation_id": sim_id,
                            "status": "completed",
                            "official_metrics": {k: v for k, v in candidate.get("official_metrics", {}).items() if k != "raw"},
                        })

                        _append_backtest_record(storage_dir, {
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
                    except BrainAPIError as exc:
                        error_text = redact_error_message(exc)
                        candidate["lifecycle_status"] = "simulation_result_failed"
                        _clear_candidate_simulation_cooldown(candidate)
                        failed += 1
                        results.append({
                            "alpha_id": alpha_id,
                            "simulation_id": sim_id,
                            "status": "result_fetch_failed",
                            "error": error_text,
                        })
                        _append_backtest_record(storage_dir, {
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
                            "progress_percent": _progress_percent(i, total, status_elapsed, poll_timeout),
                            "message": f"官方模拟结果获取失败，已等待 {status_elapsed:.1f} 秒。",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                        })
                    break

                elif status == "FAILED":
                    failure_evidence = _simulation_failure_evidence(api, sim_id)
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
                    _clear_candidate_simulation_cooldown(candidate)
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "failed",
                        "error": failure_error,
                        "failure_evidence": failure_evidence,
                    })
                    last_activity = time.monotonic()

                    _append_backtest_record(storage_dir, {
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
                    break

                # Still running, update progress
                candidate["lifecycle_status"] = "simulation_running"
                _append_backtest_record(storage_dir, {
                    "action": "polling",
                    "slot": i + 1,
                    "alpha_id": alpha_id,
                    "simulation_id": sim_id,
                    "status": status,
                    "expression": expression,
                    "poll_count": poll_attempt,
                    "poll_elapsed_seconds": round(max(0.0, status_elapsed), 1),
                    "next_poll_seconds": poll_interval,
                    "progress_percent": _progress_percent(i, total, status_elapsed, poll_timeout),
                    "message": status_message,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                })

            # Save candidates after each simulation attempt
            _save_candidate_update(storage_dir, candidate, [
                "simulation_id",
                "lifecycle_status",
                "official_alpha_id",
                "official_metrics",
                "simulation_error",
                "last_status",
                "scorecard",
                "gate",
                "cloud_correlation_risk",
                "extra_fields",
                *COOLDOWN_UPDATE_FIELDS,
            ])

        # Final status mirrors the official outcome counts so the UI never
        # treats a fully failed official batch as a successful completion.
        result_summary = {
            "total": total,
            "completed": completed,
            "failed": failed,
            "results": results,
        }
        if job_store.is_cancelled(job_id):
            final_status = "stopped"
        elif failed > 0 and completed <= 0:
            final_status = "failed"
        elif failed > 0:
            final_status = "completed_with_warnings"
        else:
            final_status = "completed"
        final_message = f"模拟完成: {completed} 成功, {failed} 失败 (共 {total})"
        update_payload: dict[str, Any] = {
            "status": final_status,
            "result": result_summary,
            "progress": {
                "phase": final_status,
                "message": final_message,
                "status_message": final_message,
                "percent": 100,
                "data": result_summary,
            },
        }
        if final_status == "failed":
            update_payload["error"] = final_message
        job_store.update(job_id, **update_payload)

    except Exception as exc:
        msg = redact_error_message(exc)
        log.exception("Simulation job failed: %s", msg)
        job_store.update(job_id, status="failed", error=msg, progress={
            "phase": "failed",
            "message": f"模拟任务失败: {msg}",
            "percent": 100,
        })


def _simulation_failure_evidence(api: Any, simulation_id: str) -> dict[str, Any]:
    """Fetch a compact, redacted failure summary for an official FAILED simulation."""
    try:
        payload = api.fetch_result(simulation_id)
    except Exception as exc:
        return {
            "simulation_id": simulation_id,
            "error": redact_error_message(exc),
            "source": "fetch_result_exception",
        }
    summary = _simulation_failure_summary(payload)
    return {
        "simulation_id": simulation_id,
        "error": summary or "official simulation returned FAILED",
        "source": "fetch_result",
    }


def _candidate_matches_requested_ids(candidate: dict[str, Any], requested_ids: set[str]) -> bool:
    if not requested_ids:
        return False
    for key in ("alpha_id", "official_alpha_id", "simulation_id"):
        value = str(candidate.get(key) or "").strip()
        if value and value in requested_ids:
            return True
    return False


def _simulation_failure_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates: list[Any] = [payload]
    raw = payload.get("raw")
    if isinstance(raw, dict):
        candidates.append(raw)
    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        candidates.append(metrics)
    for item in candidates:
        text = _first_failure_text(item)
        if text:
            return text
    return ""


def _first_failure_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in _SIMULATION_FAILURE_KEYS:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and str(value).strip():
            return redact_text(str(value).strip())[:240]
        if isinstance(value, dict):
            nested = _first_failure_text(value)
            if nested:
                return nested
    for key in ("errors", "checks", "failures"):
        values = payload.get(key)
        if isinstance(values, list):
            for row in values:
                nested = _first_failure_text(row)
                if nested:
                    return nested
    return ""


def simulation_candidates_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and prepare simulation request payload."""
    config = load_run_config()
    candidates = _load_candidates(config.ops.storage_dir)
    min_score = float(payload.get("min_score", config.ops.budget.min_prior_score_for_official_simulation))

    account_cooldown = _active_account_simulation_cooldown(config.ops.storage_dir)
    if account_cooldown:
        return {
            "ok": True,
            "eligible_count": 0,
            "total_candidates": len(candidates),
            "min_score": min_score,
            "account_cooldown": account_cooldown,
            "eligible_alphas": [],
        }

    candidate_ids = payload.get("candidate_ids")
    if candidate_ids:
        requested_ids = {str(candidate_id).strip() for candidate_id in candidate_ids if str(candidate_id).strip()}
        targets = [
            c for c in candidates
            if _candidate_matches_requested_ids(c, requested_ids) and _eligible_for_simulation(c, min_score)
        ]
    else:
        targets = [c for c in candidates if _eligible_for_simulation(c, min_score)]

    targets = _dedupe_simulation_targets(targets, default_dataset=_default_simulation_dataset(config))

    return {
        "ok": True,
        "eligible_count": len(targets),
        "total_candidates": len(candidates),
        "min_score": min_score,
        "eligible_alphas": [
            {
                "alpha_id": c.get("alpha_id", ""),
                "score": _candidate_score(c),
                "expression": (c.get("expression", "") or "")[:80],
            }
            for c in targets[:20]
        ],
    }
