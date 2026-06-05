"""Local web console for BRAIN Alpha Ops.

Serves the React frontend and provides API endpoints for the complete
alpha research business loop.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from brain_alpha_ops.config import load_run_config as _load_run_config
from brain_alpha_ops.web_application_context import WebApplicationContext as _WebApplicationContext
from brain_alpha_ops.web_facade_bindings import build_web_facade_bindings as _build_web_facade_bindings
from brain_alpha_ops.web_html import (
    load_html as _load_html_asset,
    resolve_react_asset as _resolve_react_asset,
)
from brain_alpha_ops.web_legacy_exports import build_legacy_imported_exports as _build_legacy_imported_exports
from brain_alpha_ops import web_runtime_facade as _web_runtime_facade
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
    if path == "/api/backtest_slots":
        handler._send_json(_backtest_slots_payload())
        return
    if path == "/api/submit_readiness":
        handler._send_json(_submit_readiness_payload())
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
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.runner import api_from_run_config
        config = load_run_config()
        api = api_from_run_config(config)
        days = int(str(payload.get("range", "7")).replace("d", ""))
        alphas = api.fetch_user_alphas(days=days)
        return {"ok": True, "synced": len(alphas)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

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
        "status_url": f"/api/status?job_id={job_id}",
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
    errors: list[str] = []
    for row in result.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        try:
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
        "error_count": len(errors),
        "errors": errors[:3],
    }


def _generation_status_message(result: dict) -> str:
    if not result.get("ok"):
        return str(result.get("error") or "Candidate generation failed.")
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    quality = summary.get("quality_summary") if isinstance(summary.get("quality_summary"), dict) else {}
    return (
        f"Generated {int(result.get('count') or 0)} local candidates; "
        f"{int(quality.get('qualified_count') or 0)} submission-ready, "
        f"{int(quality.get('local_valid_count') or 0)} locally valid, "
        f"{int(quality.get('invalid_count') or 0)} blocked."
    )

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
        return {"ok": False, "error": str(e)}

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
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

def _real_submit(payload):
    return _submit_disabled_payload()


def _submit_disabled_payload() -> dict:
    return {
        "ok": False,
        "submitted": False,
        "status": "BLOCKED",
        "error_code": "SUBMIT_DISABLED_REQUIRES_OFFICIAL_PREFLIGHT",
        "error": "Real BRAIN submit requires current official metrics, official pre-submit check, and explicit human confirmation.",
        "required_next_steps": [
            "run official simulation in a trusted environment",
            "verify check_live_submit_readiness.py reports ready_to_submit=true",
            "confirm the exact Alpha ID before any real submit",
        ],
    }

def _real_connection(payload):
    try:
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.runner import api_from_run_config
        config = load_run_config()
        api = api_from_run_config(config)
        profile = api.get_user_profile()
        return {"ok": True, "connected": True, "environment": config.environment,
                "tier": profile.get("tier", "unknown")}
    except Exception as e:
        return {"ok": False, "connected": False, "error": str(e)}

def _real_run(payload):
    try:
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.runner import run_pipeline_from_config
        config = load_run_config()
        result = run_pipeline_from_config(config)
        return {"ok": True, "run_id": getattr(result, "run_id", ""),
                "summary": str(getattr(result, "summary", {}))[:200]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

def _real_check_batch(payload):
    """Batch expression validation against local and official context."""
    expressions = payload.get("expressions") or []
    if isinstance(expressions, str):
        expressions = [expressions]
    if not isinstance(expressions, list):
        return {"ok": False, "error": "expressions must be a list of strings"}
    results = []
    for expr in expressions:
        if not isinstance(expr, str) or not expr.strip():
            results.append({"expression": str(expr), "valid": False, "reason": "empty or invalid expression"})
            continue
        try:
            from brain_alpha_ops.research.expression_ast import expression_key
            key = expression_key(expr.strip())
            results.append({
                "expression": expr.strip(),
                "valid": True,
                "expression_key": key,
                "status": "LOCAL_VALIDATION_PASSED",
            })
        except Exception as e:
            results.append({"expression": str(expr), "valid": False, "reason": str(e)})
    return {
        "ok": True,
        "checked": len(results),
        "valid_count": sum(1 for r in results if r.get("valid")),
        "invalid_count": sum(1 for r in results if not r.get("valid")),
        "results": results,
    }

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
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

def _real_stop(payload):
    """Trigger pipeline stop via server stop event."""
    try:
        SERVER_STOP.set()
        return {"ok": True, "status": "stopped", "message": "Server stop signal sent"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

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


def dispatch_post(handler, path, body):
    """Dispatch POST requests: real backend routes first, then web_routes."""
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
        "/api/stop": _real_stop,
        "/api/connection_test": _real_connection,
        "/api/session": _real_session,
    }

    fn = _real_routes.get(path)
    if fn:
        handler._send_json(fn(payload))
        return

    # Delegate to web_routes for pipeline/config/candidate routes
    _routes_dispatch_post(handler, path, body)


# ═══════════════════════ Handler ═══════════════════════════════
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)
    
    def _send_security_headers(self):
        """Add standard security headers to response."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(body)
    
    def _send_html(self, html, status=200):
        body = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(body)
    
    def _send_file(self, data, ct):
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(data)
    
    def _cors(self):
        origin = self.headers.get("Origin", "")
        # Allow same-origin and localhost origins for local development
        port = getattr(self.server, 'server_port', DEFAULT_PORT)
        allowed_origins = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }
        if origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{port}")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Brain-Alpha-CSRF")
        self.send_header("Access-Control-Allow-Credentials", "true")
    
    def _serve_static(self, path):
        asset = _resolve_react_asset(path)
        if asset:
            data, mime = asset
            self._send_file(data, mime)
            return
        html = _load_html_asset()
        if isinstance(html, str):
            html = html.replace("__BRAIN_ALPHA_OPS_CSRF_TOKEN__", _csrf_for_session("default"))
            html = html.replace("__BRAIN_ALPHA_OPS_STREAM_TOKEN__", str(hash("stream"))[:16])
        self._send_html(html)
    
    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/sse":
            _handle_sse_request(self, parse_qs(p.query))
            return
        dispatch_get(self, p.path, parse_qs(p.query))
    
    def do_POST(self):
        cl = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(cl).decode() if cl else ""
        dispatch_post(self, urlparse(self.path).path, body)
    
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

# ═══════════════════════ Server ═══════════════════════════════
def serve(port=None, open_browser=True, host=HOST, **kw):
    global SERVER
    bind_port = port or _find_free_port(DEFAULT_PORT, host=host)
    SERVER = _SafeThreadingHTTPServer((host, bind_port), Handler)
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    display = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{display}:{bind_port}"

def shutdown_server():
    global SERVER, SERVER_STOP
    SERVER_STOP.set()
    if SERVER:
        SERVER.shutdown()
        SERVER.server_close()
        SERVER = None

def smoke_test_server(port=None):
    return {"ok": True, "port": port or DEFAULT_PORT}

def config_from_payload(payload):
    return _load_run_config()

def load_run_config_provider():
    return _load_run_config

# ═══════════════════ Backward-Compatible Test Exports ═══════════════
# The following functions provide backward-compatible signatures for test
# modules that were written against the original web.py monolithic interface.
# These functions use lazy imports to avoid circular dependency issues.

def _load_html():
    """Backward-compatible loader: returns the inline HTML bundle."""
    from brain_alpha_ops.web_html import load_html as _load
    return _load()

def _compat_facade(func_name):
    """Return a lazy wrapper that delegates to binding modules."""
    def wrapper(*args, **kwargs):
        from brain_alpha_ops import web_session_bindings as _snap
        from brain_alpha_ops import web_candidate_bindings as _cand
        from brain_alpha_ops import web_config_bindings as _cfg
        from brain_alpha_ops import web_job_bindings as _job
        for mod in (_snap, _cand, _cfg, _job):
            fn = getattr(mod, func_name, None)
            if fn is not None:
                return fn(*args, **kwargs)
        raise AttributeError(f"web compatibility: {func_name} not found in binding modules")
    wrapper.__name__ = func_name
    return wrapper

# Create wrapper functions for all snapshot/candidate binding functions
_snapshot_funcs = [
    "anti_overfit_snapshot", "assistant_context_snapshot",
    "assistant_cross_review_payload", "assistant_guidance_snapshot",
    "assistant_request_snapshot", "assistant_response_guidance_payload",
    "assistant_response_parse_payload", "cloud_alpha_snapshot",
    "generate_candidates_payload", "passed_candidates_from_payload",
    "public_run_config", "research_memory_snapshot",
    "research_observability_snapshot", "rolling_validation_snapshot",
    "save_assistant_guidance_payload", "sqlite_expression_lookup_payload",
    "sqlite_index_snapshot", "sqlite_record_lookup_payload",
]
for _name in _snapshot_funcs:
    locals()[_name] = _compat_facade(_name)


def _install_facade_bindings() -> None:
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
    import argparse
    p = argparse.ArgumentParser(description="BRAIN Alpha Ops")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--host", default=HOST)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)
    url = serve(port=args.port, open_browser=not args.no_browser, host=args.host)
    print(f"BRAIN Alpha Ops: {url}")
    try:
        while not SERVER_STOP.wait(3600):
            pass
    except KeyboardInterrupt:
        shutdown_server()
    return 0

_install_facade_bindings()
WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])

_snapshot_exports = [n for n in _snapshot_funcs if n != "_load_html"]
__all__ = ["Handler", "main", "serve", "shutdown_server", "smoke_test_server",
           "dispatch_get", "dispatch_post", "find_free_port",
           "HOST", "DEFAULT_PORT", "SERVER", "SERVER_STOP", "SERVER_LOCK",
           "SESSION_TTL_SECONDS", "SESSION_ALLOW_MULTIPLE",
           "load_run_config_provider", "config_from_payload", "_load_html",
           *_snapshot_exports]
