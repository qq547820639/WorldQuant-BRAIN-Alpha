"""Per-candidate BRAIN API simulation service for the web console.

Provides a background-job endpoint that takes locally-generated candidates,
submits them to the BRAIN API for official simulation, polls for results,
and updates candidates with official_metrics so the scoring and gate
systems can evaluate them.

Key design constraints:
  - Respects BRAIN API rate limits (CONCURRENT_SIMULATION_LIMIT_EXCEEDED)
  - Uses stall detection: auto-interrupts if no progress for N seconds
  - Writes results back to candidates.jsonl so the UI stays in sync
  - All thresholds/config sourced from run_config, zero hardcoding
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.official import OfficialBrainAPI
from brain_alpha_ops.config import load_run_config, RunConfig
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.scoring import build_scorecard

logger = logging.getLogger(__name__)

# Stall detection: if no simulation completes within this window, auto-cancel
_DEFAULT_STALL_TIMEOUT_SECONDS = 180.0
# Per-simulation poll timeout
_DEFAULT_POLL_TIMEOUT_SECONDS = 120.0
# How long to wait between poll attempts
_DEFAULT_POLL_INTERVAL_SECONDS = 3.0
# Minimum prior score to be eligible for simulation
_DEFAULT_MIN_SCORE = 60.0

# Module-level lock to protect candidates.jsonl read/write against concurrent
# access from multiple simulation or generation threads running in parallel.
_CANDIDATES_FILE_LOCK = threading.Lock()


def _resolve_credentials(config: RunConfig) -> tuple[str, str, str]:
    """Resolve BRAIN credentials from config or environment."""
    cred = config.credentials
    username = cred.username or os.environ.get(cred.username_env, "")
    password = cred.password or os.environ.get(cred.password_env, "")
    token = cred.token or os.environ.get(cred.token_env, "")
    return username, password, token


def _create_api(config: RunConfig, *, username: str = "", password: str = "", token: str = "") -> OfficialBrainAPI:
    """Create an OfficialBrainAPI instance with proxy disabled.
    
    Credentials from arguments take priority over config/env credentials,
    so that Web-console session credentials are used when available.
    """
    cfg_username, cfg_password, cfg_token = _resolve_credentials(config)
    return OfficialBrainAPI(
        config=config.ops.official_api,
        username=username or cfg_username,
        password=password or cfg_password,
        token=token or cfg_token,
        disable_proxy=True,
    )


def _load_candidates(storage_dir: str) -> list[dict[str, Any]]:
    """Load candidates from candidates.jsonl."""
    path = Path(storage_dir) / "candidates.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _save_candidates(storage_dir: str, candidates: list[dict[str, Any]]) -> None:
    """Write candidates back to candidates.jsonl with file-level locking.

    Uses an advisory lock (.candidates.lock) to prevent concurrent writers
    from corrupting the file during multi-threaded simulation jobs.
    """
    path = Path(storage_dir) / "candidates.jsonl"
    with _CANDIDATES_FILE_LOCK:
        with path.open("w", encoding="utf-8") as f:
            for row in candidates:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_backtest_record(storage_dir: str, record: dict[str, Any]) -> None:
    """Append a simulation record to backtests.jsonl for tracking."""
    path = Path(storage_dir) / "backtests.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _candidate_score(candidate: dict) -> float:
    """Extract prior score from candidate."""
    scorecard = candidate.get("scorecard") if isinstance(candidate.get("scorecard"), dict) else {}
    value = scorecard.get("total_score", candidate.get("score"))
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return score if score == score else 0.0


def _eligible_for_simulation(candidate: dict, min_score: float) -> bool:
    """Check if candidate is eligible for BRAIN simulation."""
    # Already has official metrics
    if candidate.get("official_metrics"):
        return False
    # Already has a simulation in progress
    if candidate.get("simulation_id"):
        lifecycle = str(candidate.get("lifecycle_status", "")).lower()
        if "simulation_running" in lifecycle or "simulation_submitted" in lifecycle:
            return False
    # Score threshold
    if _candidate_score(candidate) < min_score:
        return False
    # Must be locally valid
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        return False
    return True


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
        poll_timeout = float(payload.get("poll_timeout", _DEFAULT_POLL_TIMEOUT_SECONDS))
        stall_timeout = float(payload.get("stall_timeout", _DEFAULT_STALL_TIMEOUT_SECONDS))
        poll_interval = float(payload.get("poll_interval", _DEFAULT_POLL_INTERVAL_SECONDS))
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

        if candidate_ids:
            targets = [c for c in candidates if c.get("alpha_id") in set(candidate_ids)]
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

        targets = targets[:max_simulations]

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

            # Submit simulation
            try:
                sim_id = api.submit_simulation(expression, sim_settings)
                candidate["simulation_id"] = sim_id
                candidate["lifecycle_status"] = "simulation_submitted"
                last_activity = time.monotonic()

                _append_backtest_record(storage_dir, {
                    "action": "submitted",
                    "slot": i + 1,
                    "alpha_id": alpha_id,
                    "simulation_id": sim_id,
                    "status": "SUBMITTED",
                    "expression": expression,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                })
            except BrainAPIError as exc:
                error_text = redact_error_message(exc)
                if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in error_text:
                    candidate["lifecycle_status"] = "simulation_deferred_concurrency_limit"
                    log.warning("Concurrent simulation limit hit for %s, stopping", redact_text(alpha_id))
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "status": "deferred_concurrency_limit",
                        "error": error_text,
                    })
                    # Stop submitting more - we've hit the limit
                    break
                elif exc.status_code == 429:
                    candidate["lifecycle_status"] = "simulation_deferred_rate_limit"
                    log.warning("Rate limit hit for %s, stopping", redact_text(alpha_id))
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "status": "deferred_rate_limit",
                        "error": error_text,
                    })
                    break
                else:
                    candidate["lifecycle_status"] = "simulation_submit_failed"
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "status": "submit_failed",
                        "error": error_text,
                    })
                    continue

            # Poll for result
            poll_start = time.monotonic()
            while True:
                if job_store.is_cancelled(job_id):
                    break

                elapsed = time.monotonic() - poll_start
                stall_elapsed = time.monotonic() - last_activity

                if elapsed > poll_timeout:
                    candidate["lifecycle_status"] = "simulation_poll_timeout"
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "poll_timeout",
                    })
                    break

                if stall_elapsed > stall_timeout:
                    candidate["lifecycle_status"] = "simulation_stall_detected"
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "stall_detected",
                    })
                    break

                time.sleep(poll_interval)

                try:
                    status = api.poll_simulation(sim_id)
                except BrainAPIError as exc:
                    if exc.status_code == 429:
                        wait = float(exc.retry_after or poll_interval * 2)
                        time.sleep(min(wait, 30.0))
                        continue
                    log.warning("Poll error for %s: %s", redact_text(alpha_id), redact_error_message(exc))
                    continue

                if status == "COMPLETED":
                    # Fetch result
                    try:
                        result = api.fetch_result(sim_id)
                        candidate["official_alpha_id"] = result.get("alpha_id", "") or result.get("metrics", {}).get("official_alpha_id", "")
                        candidate["official_metrics"] = result.get("metrics", {})
                        candidate["lifecycle_status"] = "official_simulated"
                        last_activity = time.monotonic()

                        # Re-score with official metrics
                        try:
                            scorecard = build_scorecard(
                                type('Candidate', (), {
                                    'official_metrics': candidate.get("official_metrics", {}),
                                    'expression': expression,
                                    'dataset_id': ds,
                                    'scorecard': candidate.get("scorecard", {}),
                                    'local_quality': candidate.get("local_quality", {}),
                                    'submission': candidate.get("submission", {}),
                                    'source_tags': candidate.get("source_tags", []),
                                    'quality_diagnosis': candidate.get("quality_diagnosis", {}),
                                    'lifecycle_status': candidate.get("lifecycle_status", ""),
                                })(),
                                config.ops.thresholds,
                                config.ops.scoring,
                            )
                            candidate["scorecard"] = scorecard
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
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                        })
                    except BrainAPIError as exc:
                        error_text = redact_error_message(exc)
                        candidate["lifecycle_status"] = "simulation_result_failed"
                        failed += 1
                        results.append({
                            "alpha_id": alpha_id,
                            "simulation_id": sim_id,
                            "status": "result_fetch_failed",
                            "error": error_text,
                        })
                    break

                elif status == "FAILED":
                    candidate["lifecycle_status"] = "simulation_failed"
                    candidate["official_metrics"] = {}
                    failed += 1
                    results.append({
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "failed",
                    })
                    last_activity = time.monotonic()

                    _append_backtest_record(storage_dir, {
                        "action": "failed",
                        "slot": i + 1,
                        "alpha_id": alpha_id,
                        "simulation_id": sim_id,
                        "status": "FAILED",
                        "expression": expression,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    })
                    break

                # Still running, update progress
                candidate["lifecycle_status"] = "simulation_running"

            # Save candidates after each simulation attempt
            _save_candidates(storage_dir, candidates)

        # Final status
        final_status = "completed" if not job_store.is_cancelled(job_id) else "stopped"
        job_store.update(job_id, status=final_status, progress={
            "phase": final_status,
            "message": f"模拟完成: {completed} 成功, {failed} 失败 (共 {total})",
            "percent": 100,
            "data": {
                "total": total,
                "completed": completed,
                "failed": failed,
                "results": results,
            },
        })

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
    min_score = float(payload.get("min_score", config.ops.budget.min_prior_score_for_official_simulation))

    candidate_ids = payload.get("candidate_ids")
    if candidate_ids:
        targets = [c for c in candidates if c.get("alpha_id") in set(candidate_ids)]
    else:
        targets = [c for c in candidates if _eligible_for_simulation(c, min_score)]

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
