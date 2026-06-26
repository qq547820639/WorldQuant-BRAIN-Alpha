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


def _real_connection(payload):
    try:
        from brain_alpha_ops.runner import api_from_run_config
        config_from_payload = _pkg()._run_config_from_payload_injected
        if config_from_payload is None:
            return {"ok": False, "error_code": "FACADE_NOT_READY",
                    "error": "configuration service is not initialized yet"}
        config = config_from_payload(_safe_non_submit_run_payload(payload))
        api = api_from_run_config(config)
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
        return _pkg()._web_error_injected(e, "CONNECTION_FAILED") if _pkg()._web_error_injected is not None else {"ok": False, "connected": False, "error": redact_error_message(e)}

def _real_run(payload):
    try:
        safe_payload = _safe_non_submit_run_payload(payload)
        # Validate before queuing so bad UI payloads fail synchronously. This
        # does not persist request credentials; run_config_from_payload only
        # applies them to the in-memory RunConfig used by this request.
        config_from_payload = _pkg()._run_config_from_payload_injected
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
        starter = _pkg()._submit_background_job_injected
        if callable(starter):
            starter(_pkg().run_job, job_id, safe_payload)  # noqa: F821
        else:
            threading.Thread(target=_pkg().run_job, args=(job_id, safe_payload), daemon=True).start()  # noqa: F821
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
        return _pkg()._web_error_injected(e, "RUN_ERROR") if _pkg()._web_error_injected is not None else {"ok": False, "error": redact_error_message(e)}


def _safe_non_submit_run_payload(payload: dict | None) -> dict:
    safe_payload = dict(payload or {})
    safe_payload["autoSubmit"] = False
    safe_payload["auto_submit"] = False
    return safe_payload


def _production_job_store():
    """Return the production job store from the web module facade.

    Uses direct attribute access on the current module's globals rather than
    sys.modules string lookup, since JOB_REGISTRY is injected at module load time.
    """
    registry = _pkg()._job_registry_injected
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
