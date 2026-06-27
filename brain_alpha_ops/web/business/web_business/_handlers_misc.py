"""Misc real backend handlers (connection, run, stop, session, security)."""

from __future__ import annotations

import logging
import sys
import threading

from brain_alpha_ops.web.security.web_session import (
    DEFAULT_SESSION_TTL_SECONDS as _SESSION_TTL_SECONDS,
)
from brain_alpha_ops.web.security.web_session import csrf_for_session as _csrf_for_session

logger = logging.getLogger("brain_alpha_ops.web.business.web_business")


def _pkg():
    return sys.modules["brain_alpha_ops.web.business.web_business"]


def _web_module():
    """Resolve the top-level ``brain_alpha_ops.web`` module (for test monkeypatch fallback)."""
    return sys.modules.get("brain_alpha_ops.web")


def _resolve_run_config_from_payload():
    """Resolve ``run_config_from_payload`` with test-monkeypatch fallback.

    Production path: use the injected dependency (set by ``inject_dependencies``).
    Test fallback: look up ``web.run_config_from_payload`` so tests that
    ``monkeypatch.setattr(web, "run_config_from_payload", ...)`` still work.
    """
    injected = _pkg()._run_config_from_payload_injected
    if callable(injected):
        return injected
    web = _web_module()
    if web is not None:
        fn = getattr(web, "run_config_from_payload", None)
        if callable(fn):
            return fn
    return None


def _resolve_web_error():
    """Resolve ``web_error`` payload helper with test-monkeypatch fallback."""
    injected = _pkg()._web_error_injected
    if callable(injected):
        return injected
    web = _web_module()
    if web is not None:
        fn = getattr(web, "_web_error", None) or getattr(web, "web_error_payload", None)
        if callable(fn):
            return fn
    return None


def _resolve_submit_background_job():
    """Resolve ``_submit_background_job`` starter with test-monkeypatch fallback."""
    injected = _pkg()._submit_background_job_injected
    if callable(injected):
        return injected
    web = _web_module()
    if web is not None:
        fn = getattr(web, "_submit_background_job", None)
        if callable(fn):
            return fn
    return None


def _resolve_run_job():
    """Resolve ``run_job`` callable with test-monkeypatch fallback."""
    web = _web_module()
    if web is not None:
        fn = getattr(web, "run_job", None)
        if callable(fn):
            return fn
    return None


def _resolve_job_registry():
    """Resolve the job registry with test-monkeypatch fallback."""
    injected = _pkg()._job_registry_injected
    if injected is not None:
        return injected
    web = _web_module()
    if web is not None:
        return getattr(web, "JOB_REGISTRY", None)
    return None


def _real_connection(payload):
    try:
        from brain_alpha_ops.runner import api_from_run_config
        config_from_payload = _resolve_run_config_from_payload()
        if config_from_payload is None:
            return {"ok": False, "error_code": "FACADE_NOT_READY",
                    "error": "configuration service is not initialized yet"}
        # test_connection accepts page-entered plaintext credentials for a
        # one-shot authentication probe; they are never persisted.
        config = config_from_payload(
            _safe_non_submit_run_payload(payload),
            allow_plaintext_credentials=True,
        )
        api = api_from_run_config(config, allow_plaintext_credentials=True)
        auth_result = api.authenticate()
        profile = api.get_user_profile() if hasattr(api, "get_user_profile") else {}
        if isinstance(profile, dict) and profile.get("error"):
            from brain_alpha_ops.brain_api.base import BrainAPIError
            try:
                status_code = int(profile.get("status_code") or 0)
            except (TypeError, ValueError):
                status_code = 0
            raise BrainAPIError(
                str(profile.get("error") or "BRAIN profile check failed"),
                status_code=status_code or None,
                payload=profile,
            )
        auth_mode = ""
        if isinstance(auth_result, dict):
            auth_mode = str(auth_result.get("auth") or "")
        return {"ok": True, "connected": True, "environment": config.environment,
                "auth": auth_mode, "tier": profile.get("tier", "unknown") if isinstance(profile, dict) else "unknown"}
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_connection failed")
        web_error = _resolve_web_error()
        if callable(web_error):
            return web_error(e, "CONNECTION_FAILED")
        return {"ok": False, "connected": False, "error": redact_error_message(e)}

def _real_run(payload):
    try:
        safe_payload = _safe_non_submit_run_payload(payload)
        # Validate before queuing so bad UI payloads fail synchronously. This
        # does not persist request credentials; run_config_from_payload only
        # applies them to the in-memory RunConfig used by this request.
        config_from_payload = _resolve_run_config_from_payload()
        if config_from_payload is None:
            return {"ok": False, "error_code": "FACADE_NOT_READY",
                    "error": "configuration service is not initialized yet"}
        config_from_payload(safe_payload)
        jobs = _production_job_store()
        if jobs is None:
            return {"ok": False, "error_code": "JOB_STORE_UNAVAILABLE", "error": "production job store is not available"}
        active = jobs.latest_active()
        if active:
            active_job_id, _job = active
            return {
                "ok": False,
                "error_code": "CONFLICT_RUNNING",
                "error": "已有生产任务正在运行，请先停止当前任务。",
                "job_id": active_job_id,
                "task_id": active_job_id,
            }
        job_id = jobs.create({
            "operation": "production_run",
            "safe_mode": {"auto_submit": False, "submit_endpoint_required": True},
            "result": {
                "summary": {
                    "submitted_this_run": 0,
                    "auto_submitted": 0,
                },
            },
            "progress": {
                "phase": "queued",
                "percent": 0,
                "percent_complete": 0,
                "message": "Non-submit production run queued.",
                "status_message": "非提交流水线已排队。",
            },
        })
        starter = _resolve_submit_background_job()
        run_job = _resolve_run_job()
        if callable(starter):
            # The starter is responsible for dispatching ``run_job`` (e.g.
            # submitting to a thread pool).  Pass ``run_job`` through even if
            # it isn't callable so test doubles can record the call.
            starter(run_job, job_id, safe_payload)
        elif callable(run_job):
            threading.Thread(target=run_job, args=(job_id, safe_payload), daemon=True).start()
        else:
            logger.warning("run_job starter unavailable; job %s queued but not started", job_id)
        return {
            "ok": True,
            "job_id": job_id,
            "task_id": job_id,
            "auto_submit": False,
            "submitted": False,
            "sse_url": f"/sse?job_id={job_id}",
            "status_url": f"/api/production-validation/status?job_id={job_id}",
        }
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("failed to start non-submit production job")
        web_error = _resolve_web_error()
        if callable(web_error):
            return web_error(e, "RUN_ERROR")
        return {"ok": False, "error": redact_error_message(e)}


def _safe_non_submit_run_payload(payload: dict | None) -> dict:
    safe_payload = dict(payload or {})
    safe_payload["autoSubmit"] = False
    safe_payload["auto_submit"] = False
    return safe_payload


def _production_job_store():
    """Return the production job store from the resolved job registry."""
    registry = _resolve_job_registry()
    return getattr(registry, "jobs", None) if registry is not None else None

def _real_stop(payload):
    """Request cancellation for the active production job."""
    try:
        job_id = str((payload or {}).get("job_id") or "")
        jobs = _production_job_store()
        if jobs is None:
            return {"ok": False, "error_code": "JOB_STORE_UNAVAILABLE", "error": "production job store is not available"}
        return {"ok": jobs.cancel(job_id), "job_id": job_id, "status": "stopping"}
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_stop failed")
        return {"ok": False, "error": redact_error_message(e)}

def _real_session(payload):
    """Create or validate a web session."""
    from brain_alpha_ops.web.security.web_session import new_session_id
    sid = new_session_id()
    csrf = _csrf_for_session(sid)
    return {
        "ok": True,
        "session_id": sid[:8],
        "csrf_token": csrf[:16],
        "ttl_seconds": _SESSION_TTL_SECONDS,  # B-04: was NameError
    }


def _has_valid_local_origin(handler) -> bool:
    """Validate request origin through handler's built-in check."""
    checker = getattr(handler, "_is_allowed_local_request", None)
    if callable(checker):
        try:
            return bool(checker())
        except (ValueError, TypeError, OSError):
            logger.warning("Origin check failed with exception, denying request", exc_info=True)
            return False
    return False  # Deny-by-default: reject if handler has no origin checker (M-SEC-04)


def _has_valid_api_session(handler) -> bool:
    """Validate session/CSRF for API routes through handler's built-in check."""
    checker = getattr(handler, "_has_valid_session", None)
    if callable(checker):
        try:
            return bool(checker(""))
        except (ValueError, TypeError, OSError):
            logger.warning("Session check failed with exception, denying request", exc_info=True)
            return False
    return False  # Safety: deny if handler has no session checker
