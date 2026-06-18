"""Runtime helpers for Web candidate official simulation jobs."""

from __future__ import annotations

import os
from typing import Any

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.official import OfficialBrainAPI
from brain_alpha_ops.config import RunConfig

# Per-simulation poll timeout fallback. The effective timeout normally comes
# from OfficialAPIConfig poll_attempts * poll_interval_seconds.
_DEFAULT_POLL_TIMEOUT_SECONDS = 120.0
# Web backtest tasks retry and poll on the same cadence so the UI can show a
# predictable elapsed-time heartbeat while waiting on official capacity.
_WEB_BACKTEST_REFRESH_SECONDS = 5.0


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


def _simulation_poll_timeout(config: RunConfig, payload: dict[str, Any]) -> float:
    if "poll_timeout" in payload:
        return max(0.0, float(payload.get("poll_timeout") or 0.0))
    api_config = getattr(getattr(config, "ops", None), "official_api", None)
    attempts = getattr(api_config, "poll_attempts", None)
    interval = getattr(api_config, "poll_interval_seconds", None)
    try:
        derived = float(attempts) * float(interval)
    except (TypeError, ValueError):
        derived = 0.0
    return max(_DEFAULT_POLL_TIMEOUT_SECONDS, derived)


def _simulation_poll_interval(config: RunConfig, payload: dict[str, Any]) -> float:
    return _WEB_BACKTEST_REFRESH_SECONDS


def _web_backtest_refresh_interval(payload: dict[str, Any]) -> float:
    return _WEB_BACKTEST_REFRESH_SECONDS


def _simulation_retry_pause_seconds(config: RunConfig, exc: BrainAPIError) -> float:
    if exc.retry_after is not None:
        try:
            return max(0.0, float(exc.retry_after))
        except (TypeError, ValueError):
            pass
    budget = getattr(getattr(config, "ops", None), "budget", None)
    try:
        return max(0.0, float(getattr(budget, "official_retry_pause_seconds", 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _progress_percent(slot_index: int, total: int, elapsed: float, poll_timeout: float) -> int:
    if total <= 0:
        return 0
    slot_progress = min(0.95, max(0.0, elapsed / max(poll_timeout, 1.0)))
    return min(95, int(((slot_index + slot_progress) / total) * 90))


def _update_simulation_progress(
    job_store: Any,
    job_id: str,
    *,
    phase: str,
    message: str,
    slot_index: int,
    total: int,
    completed: int,
    failed: int,
    alpha_id: str,
    poll_attempt: int = 0,
    poll_elapsed: float = 0.0,
    poll_timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
    last_status: str = "",
    simulation_id: str = "",
    submit_attempts: int = 0,
) -> None:
    """Record official-simulation liveness as real progress for the Web UI.

    This uses JobStore.update(), not heartbeat(), because waiting for the
    official BRAIN simulation endpoint is genuine progress in this job. Without
    these updates the generic Web watchdog may correctly see a stale job while
    the simulation worker is still polling the platform.
    """
    percent = _progress_percent(slot_index, total, poll_elapsed, poll_timeout)
    job_store.update(job_id, status="running", progress={
        "phase": phase,
        "message": message,
        "status_message": message,
        "percent": percent,
        "percent_complete": percent,
        "data": {
            "total": total,
            "completed": completed,
            "failed": failed,
            "current_alpha_id": alpha_id,
            "current_slot": slot_index + 1,
            "poll_attempt": poll_attempt,
            "poll_elapsed_seconds": round(max(0.0, poll_elapsed), 1),
            "last_status": last_status,
            "simulation_id_present": bool(simulation_id),
            "submit_attempts": max(0, int(submit_attempts or 0)),
        },
    })
