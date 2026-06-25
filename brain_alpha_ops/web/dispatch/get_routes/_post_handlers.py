"""POST route handlers for pipeline, config, candidate, and simulation endpoints."""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.redaction import redact_error_message

from ._helpers import _public_config

logger = logging.getLogger(__name__)


# ═══════════════════════ Route Handlers ═══════════════════════════════
def _handle_pipeline_start(handler: Any, payload: dict) -> None:
    """Handle pipeline start request."""
    import threading

    from brain_alpha_ops.redaction import redact_error_message
    from brain_alpha_ops.web_jobs import job_update, new_job_id

    job_id = new_job_id("pipeline")
    job_update(job_id, status="starting", progress={"phase": "init", "percent_complete": 0})

    # Start pipeline in background thread
    def run_pipeline():
        try:
            from brain_alpha_ops.brain_api.official import OfficialBrainAPI
            from brain_alpha_ops.config import load_run_config
            from brain_alpha_ops.research.pipeline import AlphaResearchPipeline

            config = load_run_config()
            ops = config.ops
            cred = config.credentials
            from brain_alpha_ops.secure_credentials import resolve_credentials
            bundle = resolve_credentials(username=cred.username, password=cred.password, token=cred.token,
                                         username_env=cred.username_env, password_env=cred.password_env, token_env=cred.token_env)
            username = bundle.username
            password = bundle.password
            token = bundle.token
            api = OfficialBrainAPI(
                config=ops.official_api,
                username=username,
                password=password,
                token=token,
                disable_proxy=True,
            )
            pipeline = AlphaResearchPipeline(config=ops, api=api)
            job_update(job_id, status="running", progress={"phase": "running", "percent_complete": 10})
            pipeline.run()
            job_update(job_id, status="completed", progress={"phase": "done", "percent_complete": 100})
        except Exception as e:
            logger.exception("Pipeline failed")
            job_update(job_id, status="failed", error=redact_error_message(e))
        finally:
            username = password = token = None

    threading.Thread(target=run_pipeline, daemon=True).start()
    handler._send_json({"ok": True, "job_id": job_id})


def _handle_pipeline_stop(handler: Any, payload: dict) -> None:
    """Reject direct stop request — production stop must go through the job monitor.

    The pipeline runs in a background thread managed by web_jobs. Stopping
    it requires coordinated cancellation via the job registry, not a simple
    thread termination. This endpoint returns a clear message guiding users
    to the correct stop mechanism.
    """
    handler._send_json({
        "ok": False,
        "error_code": "STOP_VIA_JOB_MONITOR",
        "error": "请通过页面上的任务监控面板停止流水线。直接停止请求已被拒绝以保护数据一致性。",
        "message": "Pipeline stop must use job monitor — direct stop rejected to protect data consistency.",
    }, status=409)


def _handle_config_update(handler: Any, payload: dict) -> None:
    """Handle config update request with validation.

    Only a whitelisted set of fields can be updated through the web UI.
    Nested dataclass fields (credentials, ops) are validated in depth by
    validate_run_config() after the update.
    """
    # Whitelist: only these top-level RunConfig fields are user-configurable.
    _CONFIG_UPDATE_WHITELIST = frozenset({"auto_submit", "credentials", "ops"})
    try:
        from brain_alpha_ops.config import (
            ConfigValidationError,
            validate_run_config,
            write_run_config,
        )
        config = load_run_config()
        # Update config with payload — only whitelisted fields
        rejected: list[str] = []
        for key, value in payload.items():
            if key not in _CONFIG_UPDATE_WHITELIST:
                rejected.append(key)
                continue
            if hasattr(config, key):
                setattr(config, key, value)
        # Validate before writing — rejects unsafe/out-of-range values
        validated = validate_run_config(config)
        write_run_config(validated)
        public = _public_config(validated.to_dict() if hasattr(validated, 'to_dict') else {"environment": "production"})
        response = {"ok": True, "message": "Config validated and saved", "config": public}
        if rejected:
            response["warnings"] = [f"字段 '{field}' 不支持通过 Web 修改，已忽略" for field in rejected]
        handler._send_json(response)
    except ConfigValidationError as e:
        message = redact_error_message(e)
        logger.warning("Config update validation failed: %s", message)
        handler._send_json({"ok": False, "error": message, "error_code": "CONFIG_VALIDATION_ERROR"}, status=400)
    except Exception as e:
        logger.exception("Config update failed")
        handler._send_json({"ok": False, "error": redact_error_message(e), "error_code": "CONFIG_UPDATE_ERROR"}, status=500)


def _handle_candidate_submit(handler: Any, path: str, payload: dict) -> None:
    """Reject legacy dynamic candidate-submit requests.

    The only supported submit surface is the Web staged readiness and
    confirmation flow; this compatibility route must not imply success.
    """
    # Extract candidate_id from path
    parts = path.split("/")
    if len(parts) >= 4:
        candidate_id = parts[3]
        handler._send_json(
            {
                "ok": False,
                "candidate_id": candidate_id,
                "error_code": "WEB_ONLY_SUBMIT_REQUIRED",
                "error": "Candidate submission must use the Web staged readiness and confirmation flow.",
            },
            status=410,
        )
    else:
        handler._send_json({"ok": False, "error": "invalid path"}, status=400)


def _handle_candidate_check(handler: Any, path: str, payload: dict) -> None:
    """Reject legacy single-candidate check in favor of batch check.

    Individual candidate checks are only meaningful with full context
    (API connection, cloud alphas, submission ledger).  Use the batch
    check endpoint (/api/check_batch) which orchestrates the complete
    check pipeline.
    """
    parts = path.split("/")
    if len(parts) >= 4:
        candidate_id = parts[3]
        handler._send_json(
            {
                "ok": False,
                "candidate_id": candidate_id,
                "error_code": "USE_BATCH_CHECK",
                "error": "请使用检查端点 /api/check 或批量检查端点 /api/check_batch 进行候选检查。",
                "suggestion": "POST /api/check with {\"candidate\": <candidate_object>} or POST /api/check_batch with {\"check_candidates\": [<candidate_objects>]}",
            },
            status=410,
        )
    else:
        handler._send_json({"ok": False, "error": "candidate_id is required in path", "error_code": "VALIDATION_ERROR"}, status=400)


def _handle_candidate_simulate(handler: Any, payload: dict) -> None:
    """Start BRAIN simulation for eligible candidates."""
    from brain_alpha_ops.web_candidates.simulation import (
        simulate_candidates_job,
        simulation_candidates_payload,
    )
    from brain_alpha_ops.web_jobs import job_update, new_job_id

    # Preview mode: just show eligible candidates without starting simulation
    if payload.get("preview"):
        try:
            result = simulation_candidates_payload(payload)
            handler._send_json(result)
        except Exception as exc:
            from brain_alpha_ops.redaction import redact_error_message
            handler._send_json({"ok": False, "error": redact_error_message(exc)}, status=500)
        return

    # Check for already running simulation job
    from brain_alpha_ops.web_jobs import ASYNC_JOBS, ASYNC_JOBS_LOCK
    with ASYNC_JOBS_LOCK:
        for jid, job in ASYNC_JOBS.items():
            if str(job.get("status") or "").lower() in {"queued", "pending", "running", "starting", "stopping"}:
                phase = (job.get("progress") or {}).get("phase", "")
                if "simulat" in str(phase).lower():
                    handler._send_json({
                        "ok": False,
                        "error": "已有模拟任务在运行",
                        "error_code": "CONFLICT_RUNNING",
                        "job_id": jid,
                    }, status=409)
                    return

    # Start simulation as background job. The durable JobStore-backed route uses
    # the same active initial state; keep this legacy path consistent for SSE UI.
    job_id = new_job_id("simulate")
    start_message = "正在启动官方 BRAIN 模拟任务。"
    job_update(job_id, status="running", progress={
        "phase": "simulation_starting",
        "message": start_message,
        "status_message": start_message,
        "percent": 0,
        "percent_complete": 0,
    })

    import threading
    def run_sim():
        try:
            from brain_alpha_ops.web_simulation_job import create_sim_job_store
            simulate_candidates_job(job_id, payload, job_store=create_sim_job_store(), log=logger)
        except Exception as e:
            from brain_alpha_ops.redaction import redact_error_message
            logger.exception("Simulation job %s failed", job_id)
            job_update(job_id, status="failed", error=redact_error_message(e))

    threading.Thread(target=run_sim, daemon=False).start()
    handler._send_json({
        "ok": True,
        "job_id": job_id,
        "task_id": job_id,
        "sse_url": f"/sse?job_id={job_id}",
        "status_url": f"/api/status?job_id={job_id}",
    })
