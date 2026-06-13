"""Local web console for BRAIN Alpha Ops.

Serves the React frontend and provides API endpoints for the complete
alpha research business loop.  See ``web_handler_dispatch.py`` (routes),
``web_handler_dispatch_core.py`` (dispatch loop), and
``web_facade_bindings.py`` (import-time facade surface) for the split.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from brain_alpha_ops.config import load_run_config as _load_run_config
from brain_alpha_ops import web_session as _web_session
from brain_alpha_ops.runtime_constants import WebDefaults as _WebDefaults
from brain_alpha_ops.web_application_context import WebApplicationContext as _WebApplicationContext
from brain_alpha_ops.web_facade_bindings import build_web_facade_bindings as _build_web_facade_bindings
from brain_alpha_ops.web_html import (
    load_html as _load_html_asset,
    resolve_react_asset as _resolve_react_asset,
)
from brain_alpha_ops.web_legacy_exports import build_legacy_imported_exports as _build_legacy_imported_exports
from brain_alpha_ops.web_compat_facade import install_compat_facades as _install_compat_facades, _load_html, get_snapshot_export_names as _get_snapshot_export_names
from brain_alpha_ops import web_runtime_facade as _web_runtime_facade
from brain_alpha_ops.web_cli import serve as _serve_server, shutdown_server as _shutdown_server, main as _main_cli, smoke_test_server as _smoke_test_server
from brain_alpha_ops.web_server_lifecycle import (
    SafeThreadingHTTPServer as _SafeThreadingHTTPServer,
    find_free_port as _find_free_port,
)
from brain_alpha_ops import web_routes as _web_routes
from brain_alpha_ops import web_submit_readiness as _web_submit_readiness
from brain_alpha_ops.web_routes import dispatch_get as _routes_dispatch_get
from brain_alpha_ops.web_routes import dispatch_post as _routes_dispatch_post
from brain_alpha_ops.web_jobs import job_get as _job_get, job_update as _job_update, new_job_id as _new_job_id
from brain_alpha_ops.web_service_namespace import build_web_service_namespace as _build_web_service_namespace
from brain_alpha_ops.web_session import csrf_for_session as _csrf_for_session, DEFAULT_SESSION_TTL_SECONDS as _DEFAULT_SESSION_TTL_SECONDS
from brain_alpha_ops.web_sse import handle_sse_request as _handle_sse_request

logger = logging.getLogger(__name__)
WebApplicationContext = _WebApplicationContext

# ═══════════════════════ Server config ═══════════════════════════
HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SESSION_TTL_SECONDS = _DEFAULT_SESSION_TTL_SECONDS
SESSION_ALLOW_MULTIPLE = True
SERVER_LOCK = threading.Lock()
SERVER = None
SERVER_STOP = threading.Event()

# ═══════════════════════ Dispatch ════════════════════════════════════════
# dispatch_get wraps web_routes.py for local facade compatibility.
# dispatch_post combines real backend routes + web_routes delegation.


def dispatch_get(handler, path, query):
    # ── Security: All API GET routes require valid origin ──────────
    if path.startswith("/api/") and not _has_valid_local_origin(handler):
        payload = {"ok": False, "error_code": "ORIGIN_FORBIDDEN", "error": "forbidden local request origin"}
        if hasattr(handler, "_send_json"):
            handler._send_json(payload, status=403)
        else:
            handler._json(payload, status=403)
        return
    if path == "/api/backtest_slots":
        if hasattr(handler, "_send_json"):
            handler._send_json(_backtest_slots_payload())
        else:
            handler._json(_backtest_slots_payload())
        return
    if path == "/api/submit_readiness":
        if hasattr(handler, "_send_json"):
            handler._send_json(_submit_readiness_payload())
        else:
            handler._json(_submit_readiness_payload())
        return
    _routes_dispatch_get(handler, path, query)


def _backtest_slots_payload() -> dict:
    _web_routes.load_run_config = globals().get("load_run_config", _load_run_config)
    return _web_routes._backtest_slots_payload()


def _run_live_submit_readiness_check() -> dict:
    return _web_submit_readiness.run_live_submit_readiness_check()


def _submit_readiness_payload() -> dict:
    return _web_submit_readiness.submit_readiness_payload(_run_live_submit_readiness_check)


def _compact_submit_readiness_payload(result: dict) -> dict:
    return _web_submit_readiness.compact_submit_readiness_payload(result)


def _counter_rows(counter: object, *, limit: int = 6) -> list[dict[str, int]]:
    return _web_submit_readiness.counter_rows(counter, limit=limit)


def _submit_readiness_next_steps(result: dict) -> list[str]:
    return _web_submit_readiness.submit_readiness_next_steps(result)


def _safe_int(value: object) -> int:
    return _web_submit_readiness.safe_int(value)


# ── Real backend handlers ─────────────────────────────────────────────────
def _real_sync(payload):
    try:
        from brain_alpha_ops.brain_api.user_alpha_sync import list_user_alphas_for_sync, sync_range_from_payload
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.runner import api_from_run_config
        config = load_run_config()
        api = api_from_run_config(config)
        sync_range = sync_range_from_payload(payload)
        alphas = list_user_alphas_for_sync(api, sync_range)
        return {"ok": True, "synced": len(alphas), "range": sync_range}
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_sync failed")
        return {"ok": False, "error": redact_error_message(e)}

def _real_generate(payload):
    job_id = _new_job_id("generate")
    _job_update(
        job_id,
        ok=True,
        operation="generate_candidates",
        status="running",
        progress={
            "phase": "candidate_generation",
            "status": "running",
            "status_message": "Generating local Alpha candidates and quality diagnostics.",
            "percent_complete": 5,
        },
        result=None,
    )
    thread = threading.Thread(target=_run_generate_candidates_job, args=(job_id, dict(payload or {})), daemon=True)
    thread.start()
    return {
        "ok": True,
        "job_id": job_id,
        "task_id": job_id,
        "status": "running",
        "sse_url": f"/sse?job_id={job_id}",
        "status_url": f"/api/production-validation/status?job_id={job_id}",
    }


def _run_generate_candidates_job(job_id: str, payload: dict) -> None:
    _job_update(
        job_id,
        progress={
            "phase": "candidate_generation",
            "status": "running",
            "status_message": "Applying local generation, quality gates, and output-parameter audit.",
            "percent_complete": 35,
        },
    )
    try:
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.redaction import redact_error_message
        from brain_alpha_ops.research.repository import ResearchRepository
        from brain_alpha_ops.web_candidate_generation import generate_candidates_payload
        # Initialize official data loader so local_quality() can score expressions
        from brain_alpha_ops.data import OfficialDataLoader
        OfficialDataLoader.instance()

        run_config_loader = globals().get("load_run_config", _load_run_config)
        run_config = run_config_loader()
        result = generate_candidates_payload(
            payload,
            run_config_from_payload=lambda _body: run_config,
        )
        if result.get("ok"):
            persistence = _persist_generated_candidates(job_id, run_config, result, Candidate, ResearchRepository)
            summary = result.setdefault("summary", {})
            if isinstance(summary, dict):
                summary["persistence"] = persistence
        status = "completed" if result.get("ok") else "failed"
        _job_update(
            job_id,
            ok=bool(result.get("ok")),
            status=status,
            result=result,
            error=result.get("error", ""),
            progress={
                "phase": "candidate_generation",
                "status": status,
                "status_message": _generation_status_message(result),
                "percent_complete": 100,
                "candidates_generated": int(result.get("count") or len(result.get("candidates") or [])),
                "quality_summary": (result.get("summary") or {}).get("quality_summary") if isinstance(result.get("summary"), dict) else {},
            },
        )
    except Exception as exc:
        try:
            from brain_alpha_ops.redaction import redact_error_message

            error = redact_error_message(exc)
        except Exception:
            error = str(exc)
        _job_update(
            job_id,
            ok=False,
            status="failed",
            error=error,
            result={"ok": False, "error": error, "error_code": "GENERATE_CANDIDATES_JOB_FAILED"},
            progress={
                "phase": "candidate_generation",
                "status": "failed",
                "status_message": "Candidate generation failed before quality diagnostics completed.",
                "percent_complete": 100,
                "error": error,
            },
        )


def _persist_generated_candidates(job_id: str, run_config, result: dict, candidate_type, repository_type) -> dict:
    repo = repository_type(run_config.ops.storage_dir)
    persisted = 0
    skipped_invalid = 0
    skipped_reasons: dict[str, int] = {}
    errors: list[str] = []
    for row in result.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        if not _generated_candidate_persistable(row):
            skipped_invalid += 1
            for reason in _generated_candidate_skip_reasons(row):
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            continue
        try:
            from brain_alpha_ops.web_candidate_audit import attach_scientific_audit

            if "scientific_audit" not in row and not (
                isinstance(row.get("extra_fields"), dict)
                and isinstance(row.get("extra_fields", {}).get("scientific_audit"), dict)
            ):
                row = attach_scientific_audit(
                    row,
                    operation="candidate_generation",
                    source="candidate_persistence",
                    feedback_sources=["local_quality", "scorecard", "quality_gate"],
                )
            repo.save_candidate(job_id, candidate_type.from_dict(row))
            persisted += 1
        except Exception as exc:
            try:
                from brain_alpha_ops.redaction import redact_error_message

                errors.append(redact_error_message(exc))
            except Exception:
                errors.append(str(exc))
    return {
        "schema_version": "candidate-persistence-v1",
        "target": "candidates.jsonl",
        "persisted_count": persisted,
        "skipped_invalid_count": skipped_invalid,
        "skipped_invalid_reasons": skipped_reasons,
        "error_count": len(errors),
        "errors": errors[:3],
    }


def _generated_candidate_persistable(row: dict) -> bool:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    if diagnosis.get("local_candidate_valid") is False:
        return False
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        return False
    return True


def _generated_candidate_skip_reasons(row: dict) -> list[str]:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    reasons: list[str] = []
    for reason in diagnosis.get("blocking_reasons") or []:
        text = str(reason or "").strip()
        if text:
            reasons.append(text)
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    for reason in local_quality.get("reasons") or []:
        text = str(reason or "").strip()
        if text:
            reasons.append(text.split(":", 1)[0])
    return sorted(set(reasons)) or ["local_candidate_invalid"]


def _generation_status_message(result: dict) -> str:
    if not result.get("ok"):
        return str(result.get("error") or "Candidate generation failed.")
    from brain_alpha_ops.web_candidate_generation_summary import candidate_generation_status_message

    return candidate_generation_status_message(result)

def _real_check(payload):
    try:
        from brain_alpha_ops.research.expression_ast import expression_key
        expr = payload.get("expression", "")
        key = expression_key(expr)
        return {
            "ok": True,
            "local_only": True,
            "official_api_called": False,
            "available": True,
            "expression_key": key,
            "status": "LOCAL_EXPRESSION_CHECK_ONLY",
            "requires_official_check": True,
        }
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_check failed")
        return {"ok": False, "error": redact_error_message(e)}

def _real_score(payload):
    try:
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.research.scoring import build_scorecard
        from brain_alpha_ops.models import Candidate
        config = load_run_config()
        expr = payload.get("expression", "")
        candidate = Candidate(expression=expr, alpha_id='', family='', hypothesis='')
        scorecard = build_scorecard(candidate, config.ops.thresholds, config.ops.scoring)
        return {"ok": True, "scoring": {
            "sharpe": float(scorecard.get("sharpe", 0) if isinstance(scorecard, dict) else getattr(scorecard, "sharpe", 0)),
            "fitness": float(scorecard.get("fitness", 0) if isinstance(scorecard, dict) else getattr(scorecard, "fitness", 0)),
            "local_score": float(scorecard.get("local_score", 0) if isinstance(scorecard, dict) else getattr(scorecard, "local_score", 0)),
        }}
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_score failed")
        return {"ok": False, "error": redact_error_message(e)}

def _real_submit(payload):
    return _submit_disabled_payload()


def _submit_disabled_payload() -> dict:
    return {
        "ok": False,
        "submitted": False,
        "status": "BLOCKED",
        "error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW",
        "error": "真实提交已从普通 Web 流程关闭；请先完成提交前阻断复核，如确需提交需走单独审批路径。",
        "required_next_steps": [
            "完成官方上下文刷新和提交前阻断复核",
            "确认候选具备官方 Alpha ID 与完整官方指标",
            "如需真实提交，由维护者在单独审批路径中执行",
        ],
    }

def _real_connection(payload):
    try:
        from brain_alpha_ops.runner import api_from_run_config
        config_from_payload = globals().get("run_config_from_payload")
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
        return _web_error(e, "CONNECTION_FAILED") if "_web_error" in globals() else {"ok": False, "connected": False, "error": redact_error_message(e)}

def _real_run(payload):
    try:
        safe_payload = _safe_non_submit_run_payload(payload)
        # Validate before queuing so bad UI payloads fail synchronously. This
        # does not persist request credentials; run_config_from_payload only
        # applies them to the in-memory RunConfig used by this request.
        config_from_payload = globals().get("run_config_from_payload")
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
        starter = globals().get("_submit_background_job")
        if callable(starter):
            starter(run_job, job_id, safe_payload)
        else:
            threading.Thread(target=run_job, args=(job_id, safe_payload), daemon=True).start()
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
        return _web_error(e, "RUN_ERROR") if "_web_error" in globals() else {"ok": False, "error": redact_error_message(e)}


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
    registry = globals().get("JOB_REGISTRY")
    return getattr(registry, "jobs", None) if registry is not None else None

def _real_check_batch(payload):
    """Batch expression validation delegating to web_check_batch_context."""
    from brain_alpha_ops.web_check_batch_context import check_batch_official_context_payload

    # Resolve through globals so tests can monkeypatch web.load_run_config.
    loader = globals().get("load_run_config", _load_run_config)
    return check_batch_official_context_payload(payload, load_run_config=loader)

def _real_submit_batch(payload):
    """Batch submit with safety gates — real submission requires pre-flight checks."""
    return _submit_disabled_payload()

def _real_attribution(payload):
    """Real score attribution from the scoring system."""
    try:
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        config = load_run_config()
        expression = payload.get("expression", "")
        if not expression:
            return {"ok": False, "error": "expression is required"}

        candidate = Candidate(expression=expression, alpha_id="", family="", hypothesis="")
        oss = OfficialScoringSystem(config.ops)
        result = oss.evaluate(candidate)

        return {
            "ok": True,
            "attribution": result.to_dict(),
            "report": result.attribution_report(),
        }
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_attribution failed")
        return {"ok": False, "error": redact_error_message(e)}

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
    from brain_alpha_ops.web_session import csrf_for_session, new_session_id
    sid = new_session_id()
    csrf = _csrf_for_session(sid)
    return {
        "ok": True,
        "session_id": sid[:8],
        "csrf_token": csrf[:16],
        "ttl_seconds": SESSION_TTL_SECONDS,
    }


def _has_valid_local_origin(handler) -> bool:
    """Validate request origin through handler's built-in check."""
    checker = getattr(handler, "_is_allowed_local_request", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            logger.warning("Origin check failed with exception, denying request", exc_info=True)
            return False
    return False  # Deny-by-default: reject if handler has no origin checker (M-SEC-04)


def _has_valid_api_session(handler) -> bool:
    """Validate session/CSRF for API routes through handler's built-in check."""
    checker = getattr(handler, "_has_valid_session", None)
    if callable(checker):
        try:
            return bool(checker(""))
        except Exception:
            logger.warning("Session check failed with exception, denying request", exc_info=True)
            return False
    return False  # Safety: deny if handler has no session checker


def dispatch_post(handler, path, body):
    """Dispatch POST requests: real backend routes first, then web_routes.

    Security (R-01 fix): All POST API routes now require valid session + origin
    validation, aligning with web_handler_dispatch.py security layer.
    The only exempt route is /api/session (creates new sessions).
    """
    # ── Security: Origin validation ──────────────────────────────────
    if not _has_valid_local_origin(handler):
        payload = {"ok": False, "error_code": "ORIGIN_FORBIDDEN", "error": "forbidden local request origin"}
        if hasattr(handler, "_send_json"):
            handler._send_json(payload, status=403)
        else:
            handler._json(payload, status=403)
        return

    # ── Security: Session validation ─────────────────────────────────
    # /api/session is the only route that doesn't require a pre-existing session
    if path != "/api/session" and not _has_valid_api_session(handler):
        payload = {"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}
        if hasattr(handler, "_send_json"):
            handler._send_json(payload, status=403)
        else:
            handler._json(payload, status=403)
        return

    # ── Security: Replay protection (M-SEC-03) ───────────────────────
    if path != "/api/session":
        replay_validator = getattr(handler, "_validate_replay_request", None)
        if callable(replay_validator):
            replay_result = replay_validator()
            if not replay_result.get("ok"):
                status = 409 if replay_result.get("error_code") == "REPLAY_DETECTED" else 400
                handler._send_json({"ok": False, **replay_result}, status=status) if hasattr(handler, "_send_json") else handler._json({"ok": False, **replay_result}, status=status)
                return

    payload = {}
    if body:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            pass

    # Real backend routes (unique to this module)
    _real_routes = {
        "/api/sync-cloud-alphas": _real_sync,
        "/api/generate_candidates": _real_generate,
        "/api/check": _real_check,
        "/api/check_batch": _real_check_batch,
        "/api/submit": _real_submit,
        "/api/submit_batch": _real_submit_batch,
        "/api/scoring/evaluate": _real_score,
        "/api/scoring/attribution": _real_attribution,
        "/api/run": _real_run,
        "/api/production-validation/start": _real_run,
        "/api/stop": _real_stop,
        "/api/production-validation/stop": _real_stop,
        "/api/test_connection": _real_connection,
        "/api/connection_test": _real_connection,
        "/api/session": _real_session,
    }

    fn = _real_routes.get(path)
    if fn:
        if hasattr(handler, "_send_json"):
            handler._send_json(fn(payload))
        else:
            handler._json(fn(payload))
        return

    # Delegate to web_routes for pipeline/config/candidate routes
    _routes_dispatch_post(handler, path, body)


# ═══════════════════════ Handler ═══════════════════════════════
class Handler(BaseHTTPRequestHandler):
    _MAX_BODY_BYTES = _WebDefaults.MAX_BODY_BYTES

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)

    def _session_id_from_cookie(self):
        return _web_session.session_id_from_cookie(str(self.headers.get("Cookie", "")))

    def _has_valid_session(self, query_string=""):
        csrf_header = str(
            self.headers.get("X-Brain-Alpha-CSRF", "")
            or self.headers.get("X-CSRF-Token", "")
            or self.headers.get("X-CSRF", "")
        )
        return _web_session.has_valid_request_session(
            path=urlparse(self.path).path,
            query_string=query_string,
            csrf_header=csrf_header,
            cookie_header=str(self.headers.get("Cookie", "")),
        )

    def _validate_replay_request(self):
        return _web_session.validate_replay_request(
            session_id=self._session_id_from_cookie(),
            request_id=str(self.headers.get("X-Brain-Alpha-Request-ID", "")),
            request_timestamp=str(self.headers.get("X-Brain-Alpha-Request-Timestamp", "")),
        )

    def _is_allowed_local_request(self):
        return _web_session.is_allowed_request(
            host_header=str(self.headers.get("Host", "")),
            origin_header=str(self.headers.get("Origin", "")),
            referer_header=str(self.headers.get("Referer", "")),
        )

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0:
            raise ValueError("invalid request body length")
        if length > self._MAX_BODY_BYTES:
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _handle_sse_stream(self, query_string):
        if not self._has_valid_session(query_string):
            self._json({"ok": False, "error_code": "AUTH_REQUIRED", "error": "session required"}, status=401)
            return
        _handle_sse_request(self, parse_qs(query_string))

    def _html(self, html, *, extra_headers=None):
        self._send_html(html, extra_headers=extra_headers)

    def _json(self, payload, status=200, *, extra_headers=None):
        self._send_json(payload, status=status, extra_headers=extra_headers)
    
    def _send_security_headers(self, html=None):
        """Add standard security headers to response (P1-2: includes CSP)."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        # Lazy import: web_csp uses re + hashlib only, safe to import here.
        from brain_alpha_ops.web_csp import content_security_policy_for_html as _csp_for_html
        self.send_header("Content-Security-Policy", _csp_for_html(html or ""))

    def _send_html(self, html, *, extra_headers=None):
        """Send HTML response with security headers."""
        body = html.encode("utf-8") if isinstance(html, str) else html
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_security_headers(html=html)
        if extra_headers:
            for name, value in extra_headers:
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload, status=200, *, extra_headers=None):
        """Send JSON response with security headers."""
        import json as _json_module
        body = _json_module.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_security_headers()
        if extra_headers:
            for name, value in extra_headers:
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

def _json_default(obj):
    """Safe JSON default for module-level dispatch helpers."""
    from datetime import datetime, date
    from decimal import Decimal
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    import logging
    logging.getLogger(__name__).warning(
        "JSON fallback: %s of type %s", repr(obj)[:100], type(obj).__name__
    )
    return repr(obj)

# ═══════════════════════ Server ═══════════════════════════════
def serve(port=None, open_browser=True, host=HOST, **kw):
    with SERVER_LOCK:
        global SERVER
        url = _serve_server(
            port=port, open_browser=open_browser, host=host,
            default_port=DEFAULT_PORT, handler_class=Handler,
            _SafeThreadingHTTPServer=_SafeThreadingHTTPServer,
            _find_free_port=_find_free_port,
            **kw,
        )
        SERVER = _serve_server._SERVER if hasattr(_serve_server, '_SERVER') else None  # type: ignore[attr-defined]
    return url

def shutdown_server():
    with SERVER_LOCK:
        global SERVER
        _shutdown_server(server=SERVER, server_stop=SERVER_STOP)
        SERVER = None

def smoke_test_server(port=None):
    return _smoke_test_server(port=port if port is not None else DEFAULT_PORT)

def config_from_payload(payload):
    return _load_run_config()

def load_run_config_provider():
    return _load_run_config

# ═══════════════════ Backward-Compatible Test Exports ═══════════════
# The following functions provide backward-compatible signatures for test
# modules that were written against the original web.py monolithic interface.
# These functions use lazy imports to avoid circular dependency issues.
# Backward-compatible facade wrappers installed from web_compat_facade
_install_compat_facades(locals())


def _install_facade_bindings() -> None:
    """Install three distinct facade surfaces into this module's globals.

    Three surfaces coexist on purpose (P1-6 doc — do NOT consolidate):

    1. ``web_service_namespace.build_web_service_namespace`` (legacy
       import-time facade): provides backwards-compatible top-level symbols
       for tests and external scripts that historically did
       ``from brain_alpha_ops.web import X``.

    2. ``web_runtime_facade``: lazy runtime facade used by
       ``web_service_namespace`` for ``compute_run_stats`` and
       ``status_category``; not intended to be the production dispatch path.

    3. ``web_facade_bindings.build_web_facade_bindings``: extended facade
       used by the factory ``Handler`` defined in ``web_http_handler.py``
       for the (latent) alt-dispatch path.  Production dispatch is still
       the in-line ``Handler`` defined in this module (the factory is
       reserved for future enablement).

    See ``web_handler_dispatch.py`` for the route table and
    ``web_handler_dispatch_core.py`` for the dispatch loop.
    """
    namespace = _build_web_service_namespace()
    globals().update(namespace)
    globals()["_runtime_facade"] = _web_runtime_facade
    globals().update(_build_web_facade_bindings(globals()))
    globals()["_LEGACY_IMPORTED_EXPORTS"] = _build_legacy_imported_exports(globals())


def web_application_context():
    return WEB_APPLICATION_CONTEXT


def _app_context():
    return WEB_APPLICATION_CONTEXT


def __getattr__(name: str):
    if name == "JOBS":
        return JOB_REGISTRY.jobs
    if name == "SYNC_JOBS":
        return JOB_REGISTRY.sync_jobs
    if name == "CHECK_JOBS":
        return JOB_REGISTRY.check_jobs
    if name == "ASYNC_JOBS":
        return JOB_REGISTRY.async_jobs
    if name == "SUBMIT_LOCK":
        return JOB_REGISTRY.submit_lock
    if name == "RATE_LIMITER":
        return JOB_REGISTRY.rate_limiter
    if name == "TASK_EXECUTOR":
        return JOB_REGISTRY.task_executor
    legacy = _LEGACY_IMPORTED_EXPORTS.get(name)
    if legacy is not None:
        return legacy
    raise AttributeError(name)

def main(argv=None):
    return _main_cli(
        argv=argv, serve_fn=serve, shutdown_fn=shutdown_server,
        host=HOST, server_stop=SERVER_STOP,
    )

_install_facade_bindings()
WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])

_snapshot_exports = _get_snapshot_export_names()
__all__ = ["Handler", "main", "serve", "shutdown_server", "smoke_test_server",
           "dispatch_get", "dispatch_post", "find_free_port",
           "HOST", "DEFAULT_PORT", "SERVER", "SERVER_STOP", "SERVER_LOCK",
           "SESSION_TTL_SECONDS", "SESSION_ALLOW_MULTIPLE",
           "load_run_config_provider", "config_from_payload", "_load_html",
           *_snapshot_exports]
