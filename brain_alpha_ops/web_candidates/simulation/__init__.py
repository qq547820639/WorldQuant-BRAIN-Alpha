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

Subpackage split (formerly ``simulation.py`` monolith):
  - ``__init__``: public API, orchestration, re-exports
  - ``_submit``: candidate submission loop with retry/concurrency handling
  - ``_poll``: polling loop with timeout/stall detection
  - ``_results``: COMPLETED/FAILED result handlers
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace
from typing import Any

from brain_alpha_ops.brain_api.base import BrainAPIError  # noqa: F401
from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.redaction import redact_error_message, redact_text  # noqa: F401
from brain_alpha_ops.web_candidates.audit import append_scientific_audit_event  # noqa: F401
from brain_alpha_ops.web_candidates.simulation_failures import (  # noqa: F401
    append_official_simulation_audit as _append_official_simulation_audit,
    simulation_failure_evidence as _simulation_failure_evidence,
)
from brain_alpha_ops.web_candidates.simulation_runtime import (  # noqa: F401
    _create_api,
    _progress_percent,
    _simulation_poll_interval,
    _simulation_poll_timeout,
    _simulation_retry_pause_seconds,
    _update_simulation_progress,
    _web_backtest_refresh_interval,
)
from brain_alpha_ops.web_candidates.simulation_selection import (  # noqa: F401
    candidate_matches_requested_ids as _candidate_matches_requested_ids,
    requested_candidate_ids_from_payload as _requested_candidate_ids_from_payload,
    simulation_candidates_payload as _simulation_candidates_payload,
)
from brain_alpha_ops.web_candidates.simulation_state import (  # noqa: F401
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
)

from ._poll import _run_polling_loop
from ._submit import _run_submission_loop

logger = logging.getLogger(__name__)

# Stall detection: if no simulation completes within this window, auto-cancel
_DEFAULT_STALL_TIMEOUT_SECONDS = 180.0
# Minimum prior score to be eligible for simulation
_DEFAULT_MIN_SCORE = 60.0


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
      3. Fills up to the configured official simulation slots
      4. Polls submitted slots round-robin with stall detection
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
        max_concurrent = int(getattr(budget, "max_official_concurrent_simulations", 3) or 3)
        slot_limit = max(0, min(max_simulations, max_concurrent))
        poll_timeout = _simulation_poll_timeout(config, payload)
        stall_timeout = float(payload.get("stall_timeout", _DEFAULT_STALL_TIMEOUT_SECONDS))
        poll_interval = _web_backtest_refresh_interval(payload)
        candidate_ids = _requested_candidate_ids_from_payload(payload)

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
            targets = sorted(targets, key=_candidate_score, reverse=True)
        else:
            targets = sorted(
                (c for c in candidates if _eligible_for_simulation(c, min_score)),
                key=_candidate_score,
                reverse=True,
            )

        if not targets:
            job_store.update(job_id, status="completed", progress={
                "phase": "no_eligible",
                "message": f"没有符合条件的候选Alpha (最低分数: {min_score})。",
                "percent": 100,
                "data": {"total_candidates": len(candidates), "eligible": 0},
            })
            return

        if job_store.is_cancelled(job_id):
            job_store.update(job_id, status="stopped", progress={
                "phase": "stopped",
                "message": "官方模拟任务已在远程 API 初始化前停止。",
                "status_message": "官方模拟任务已在远程 API 初始化前停止。",
                "percent": 100,
                "percent_complete": 100,
                "data": {"total_candidates": len(candidates), "eligible": len(targets)},
            })
            return

        default_dataset = _default_simulation_dataset(config)
        deduped_targets = _dedupe_simulation_targets(targets, default_dataset=default_dataset)
        eligible_count = len(deduped_targets)
        targets = deduped_targets[:slot_limit]
        if not targets:
            job_store.update(job_id, status="completed", progress={
                "phase": "no_simulation_slots",
                "message": "当前没有可用的官方模拟槽位。",
                "percent": 100,
                "data": {"total_candidates": len(candidates), "eligible": eligible_count, "slot_limit": slot_limit},
            })
            return

        if job_store.is_cancelled(job_id):
            job_store.update(job_id, status="stopped", progress={
                "phase": "stopped",
                "message": "官方模拟任务已在远程 API 初始化前停止。",
                "status_message": "官方模拟任务已在远程 API 初始化前停止。",
                "percent": 100,
                "percent_complete": 100,
                "data": {"total_candidates": len(candidates), "eligible": eligible_count, "slot_limit": slot_limit},
            })
            return

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

        update_fields = [
            "simulation_id",
            "lifecycle_status",
            "official_alpha_id",
            "official_metrics",
            "simulation_error",
            "last_status",
            "scorecard",
            "gate",
            "cloud_correlation_risk",
            "scientific_audit",
            "extra_fields",
            *COOLDOWN_UPDATE_FIELDS,
        ]
        cooldown_audit_update_fields = [*COOLDOWN_UPDATE_FIELDS, "scientific_audit"]
        terminal_audit_update_fields = [field for field in update_fields if field != "extra_fields"]

        active_slots: list[dict[str, Any]] = []
        stop_new_submissions = False

        state = SimpleNamespace(
            job_store=job_store,
            job_id=job_id,
            log=log,
            api=api,
            config=config,
            storage_dir=storage_dir,
            settings=settings,
            total=total,
            completed=completed,
            failed=failed,
            last_activity=last_activity,
            results=results,
            active_slots=active_slots,
            stop_new_submissions=stop_new_submissions,
            poll_timeout=poll_timeout,
            stall_timeout=stall_timeout,
            poll_interval=poll_interval,
            update_fields=update_fields,
            cooldown_audit_update_fields=cooldown_audit_update_fields,
            terminal_audit_update_fields=terminal_audit_update_fields,
        )

        _run_submission_loop(state, targets=targets)
        _run_polling_loop(state)

        # Final status mirrors the official outcome counts so the UI never
        # treats a fully failed official batch as a successful completion.
        result_summary = {
            "total": total,
            "completed": state.completed,
            "failed": state.failed,
            "results": state.results,
        }
        if job_store.is_cancelled(job_id):
            final_status = "stopped"
        elif state.failed > 0 and state.completed <= 0:
            final_status = "failed"
        elif state.failed > 0:
            final_status = "completed_with_warnings"
        else:
            final_status = "completed"
        final_message = f"模拟完成: {state.completed} 成功, {state.failed} 失败 (共 {total})"
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


def simulation_candidates_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and prepare simulation request payload."""
    config = load_run_config()
    candidates = _load_candidates(config.ops.storage_dir)
    return _simulation_candidates_payload(
        payload,
        config=config,
        candidates=candidates,
        account_cooldown=_active_account_simulation_cooldown(config.ops.storage_dir),
        eligible_for_simulation=_eligible_for_simulation,
        candidate_score=_candidate_score,
        dedupe_simulation_targets=_dedupe_simulation_targets,
        default_dataset=_default_simulation_dataset(config),
    )


__all__ = [
    "simulate_candidates_job",
    "simulation_candidates_payload",
]
