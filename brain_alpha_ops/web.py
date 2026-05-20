"""Tiny local web console for BRAIN Alpha Ops.

The server uses only Python's standard library. It is intentionally local-only
and keeps credentials in memory for the current request.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import json
import logging
from pathlib import Path
import threading
import time

logger = logging.getLogger(__name__)

from brain_alpha_ops.config import (
    RunConfig,
    load_run_config,
    runtime_project_root,
)
from brain_alpha_ops.web_config import (
    _MAX_BACKTEST_BATCH_SIZE,
    _MAX_CANDIDATES,
    _MAX_CONCURRENT_SIMULATIONS,
    _MAX_CYCLES,
    _MAX_CYCLE_PAUSE_SECONDS,
    _MAX_POOL_SIZE,
    _MAX_SIMULATIONS,
    _MAX_VALIDATIONS,
    bounded_query_float as _bounded_query_float,
    bounded_query_int as _bounded_query_int,
    config_from_payload as _config_from_payload,
    payload_truthy,
    run_config_from_payload as _run_config_from_payload,
)
from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS, DEFAULT_OPERATORS
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.jsonl import tail_text_lines
from brain_alpha_ops.models import utc_now
from brain_alpha_ops.observability import error_payload
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.guidance import (
    assistant_guidance_outcome_status,
)
from brain_alpha_ops.task_executor import ThreadTaskExecutor
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger, mock_source_reasons
from brain_alpha_ops.runner import api_from_run_config, run_pipeline_from_config
from brain_alpha_ops.tasks import JobStore as DurableJobStore
from brain_alpha_ops.web_assistant_snapshots import (
    assistant_context_snapshot as _assistant_context_snapshot_service,
    assistant_guidance_history as _assistant_guidance_history_service,
    assistant_guidance_snapshot as _assistant_guidance_snapshot_service,
    assistant_request_snapshot as _assistant_request_snapshot_service,
    assistant_response_guidance_payload as _assistant_response_guidance_payload_service,
    assistant_response_parse_payload as _assistant_response_parse_payload_service,
    durable_job_rows as _durable_job_rows_service,
    latest_result_snapshot as _latest_result_snapshot_service,
    latest_run_history_path as _latest_run_history_path_service,
    prompt_run_ledger_snapshot as _prompt_run_ledger_snapshot_service,
    research_knowledge_snapshot as _research_knowledge_snapshot_service,
    research_memory_snapshot as _research_memory_snapshot_service,
    research_observability_snapshot as _research_observability_snapshot_service,
    save_assistant_guidance_payload as _save_assistant_guidance_payload_service,
    user_profile_snapshot as _user_profile_snapshot_service,
)
from brain_alpha_ops.web_check_availability import (
    check_candidate_availability as _check_candidate_availability,
    cloud_row_expression as _cloud_row_expression,
    cloud_similarity_risk as _cloud_similarity_risk,
    cloud_status_for as _cloud_status_for,
)
from brain_alpha_ops.web_check_batch_job import run_check_batch_job_service
from brain_alpha_ops.web_cloud_snapshot import (
    cloud_alpha_snapshot as _cloud_alpha_snapshot_service,
    cloud_alpha_summary as _cloud_alpha_summary_service,
    datasets_from_fields as _datasets_from_fields_service,
    dedupe_cloud_alpha_rows as _dedupe_cloud_alpha_rows_service,
    drop_mock_rows_if_real as _drop_mock_rows_if_real_service,
    latest_cached_user_alpha_path as _latest_cached_user_alpha_path_service,
    latest_cached_user_alphas as _latest_cached_user_alphas_service,
    official_context_file_counts as _official_context_file_counts_service,
    path_modified_at as _path_modified_at_service,
    persist_official_context as _persist_official_context_service,
    read_official_context_json as _read_official_context_json_service,
    read_storage_jsonl as _read_storage_jsonl_service,
    read_storage_jsonl_stats as _read_storage_jsonl_stats_service,
    save_official_context_json as _save_official_context_json_service,
    storage_jsonl_path as _storage_jsonl_path_service,
)
from brain_alpha_ops.web_candidate_check import check_candidate_payload
from brain_alpha_ops.web_candidate_generation import generate_candidates_payload as _generate_candidates_payload
from brain_alpha_ops.web_candidate_selection import (
    candidate_from_payload as _candidate_from_payload,
    candidate_official_metrics,
    is_passed_candidate_for_check,
    official_alpha_id,
    passed_candidates_from_payload as _passed_candidates_from_payload,
)
from brain_alpha_ops.web_cloud_context_refresh import refresh_cloud_context_for_check_service
from brain_alpha_ops.web_get_handlers import (
    active_job_payload,
    health_payload,
    job_status_payload,
    lifecycle_payload,
    presets_payload,
    profile_payload,
)
from brain_alpha_ops.web_post_handlers import (
    assistant_response_guidance_post_payload,
    assistant_response_parse_post_payload,
    background_job_start_payload,
    connection_test_post_payload,
    save_assistant_guidance_post_payload,
    session_end_payload,
    stop_job_payload,
)
from brain_alpha_ops.web_review_api import (
    anti_overfit_snapshot as _anti_overfit_snapshot_service,
    assistant_cross_review_payload as _assistant_cross_review_payload_service,
    rolling_validation_snapshot as _rolling_validation_snapshot_service,
)
from brain_alpha_ops.web_handler_dispatch import WebHandlerDispatchContext, dispatch_get, dispatch_post
from brain_alpha_ops.web_routes import route_for
from brain_alpha_ops.web_run_job import run_guided_job_service, run_job_service
from brain_alpha_ops.web_runtime_state import (
    active_auxiliary_operation as _active_auxiliary_operation_service,
    compute_run_stats as _compute_run_stats_service,
    lifecycle_from_job as _lifecycle_from_job_service,
    load_check_results as _load_check_results_service,
    load_presets as _load_presets_service,
    match_preset_id as _match_preset_id_service,
    maybe_archive_lifecycle as _maybe_archive_lifecycle_service,
    status_category as _status_category_service,
)
from brain_alpha_ops.web_security import (
    LOCAL_HOSTS,
    LOOPBACK_BIND_HOSTS,
    SESSION_COOKIE_NAME,
    LocalSessionManager,
    header_hostname as _header_hostname_service,
    header_port as _header_port_service,
    is_allowed_local_request as _is_allowed_local_request_service,
    normalize_host as _normalize_host_service,
    parse_cookies as _parse_cookies_service,
    path_requires_session as _path_requires_session_service,
)
from brain_alpha_ops.web_server_lifecycle import (
    find_free_port as _find_free_port_service,
    serve as _serve_service,
    shutdown_server as _shutdown_server_service,
    smoke_test_server as _smoke_test_server_service,
)
from brain_alpha_ops.web_sqlite_indexes import (
    sqlite_expression_lookup_payload as _sqlite_expression_lookup_payload_service,
    sqlite_index_snapshot as _sqlite_index_snapshot_service,
    sqlite_record_lookup_payload as _sqlite_record_lookup_payload_service,
)
from brain_alpha_ops.web_submission_batch import submit_batch_payload
from brain_alpha_ops.web_submission_single import submit_candidate_payload
from brain_alpha_ops.web_submission_safety import (
    observability_submission_preflight as _observability_submission_preflight,
    submission_preflight_advisory as _submission_preflight_advisory,
    submit_preflight_block as _submission_preflight_block_service,
)
from brain_alpha_ops.web_sync_job import run_sync_job_service
from brain_alpha_ops.web_sync_payload import sync_cloud_alphas_payload


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
CLOUD_SYNC_STALE_SECONDS = 24 * 60 * 60
SESSION_TTL_SECONDS = 12 * 60 * 60
SESSION_ALLOW_MULTIPLE = True
SESSION_MANAGER = LocalSessionManager(ttl_seconds=SESSION_TTL_SECONDS, allow_multiple_sessions=SESSION_ALLOW_MULTIPLE)
SESSIONS = SESSION_MANAGER.sessions
SESSION_LOCK = SESSION_MANAGER.lock

# Allowed base URLs per environment — used to prevent SSRF via frontend.
HTML = _HTML_CACHE = ""


def _header_hostname(host_header: str) -> str:
    return _header_hostname_service(host_header)


def _header_port(host_header: str) -> int | None:
    return _header_port_service(host_header)


def _path_requires_session(path: str) -> bool:
    return _path_requires_session_service(path)


def configure_session_policy(ttl_seconds: int | float | None = None, allow_multiple_sessions: bool | None = None) -> None:
    global SESSION_TTL_SECONDS, SESSION_ALLOW_MULTIPLE
    SESSION_MANAGER.configure(ttl_seconds, allow_multiple_sessions)
    SESSION_TTL_SECONDS = SESSION_MANAGER.ttl_seconds
    SESSION_ALLOW_MULTIPLE = SESSION_MANAGER.allow_multiple_sessions


def _parse_cookies(cookie_header: str) -> dict[str, str]:
    return _parse_cookies_service(cookie_header)


def _session_cookie_header(session_id: str, *, max_age: int | None = None) -> str:
    return SESSION_MANAGER.cookie_header(session_id, max_age=max_age)


def _expired_session_cookie_header() -> str:
    return SESSION_MANAGER.expired_cookie_header()


def _prune_sessions(now: float | None = None) -> None:
    SESSION_MANAGER.prune(now)


def _create_session() -> tuple[str, str]:
    return SESSION_MANAGER.create()


def _expire_session(session_id: str) -> None:
    SESSION_MANAGER.expire(session_id)


def _validate_session_token(session_id: str, token: str, token_key: str) -> bool:
    return SESSION_MANAGER.validate_token(session_id, token, token_key)


def _validate_session(session_id: str, csrf_token: str) -> bool:
    return SESSION_MANAGER.validate_csrf(session_id, csrf_token)


def _validate_stream_session(session_id: str, stream_token: str) -> bool:
    return SESSION_MANAGER.validate_stream(session_id, stream_token)


def _csrf_for_session(session_id: str) -> str:
    return SESSION_MANAGER.csrf_for_session(session_id)


def _stream_token_for_session(session_id: str) -> str:
    return SESSION_MANAGER.stream_token_for_session(session_id)


def _get_or_create_session(existing_session_id: str) -> tuple[str, str]:
    return SESSION_MANAGER.get_or_create(existing_session_id)


def safe_error_message(exc: Exception) -> str:
    message = redact_error_message(exc)
    lowered = message.lower()
    if "production mode requires" in lowered:
        return "production mode requires BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN"
    if any(marker in lowered for marker in ("authorization", "cookie", "token", "password")):
        return "Authentication failed; check credentials or connection settings."
    return message


def safe_error_payload(exc: Exception, *, error_code: str = "UNHANDLED_ERROR") -> dict:
    payload = user_error_payload(exc, error_code=error_code)
    payload["error"] = safe_error_message(exc)
    return payload


def _web_error(exc: Exception, error_code: str) -> dict:
    return safe_error_payload(exc, error_code=error_code)


def _load_html() -> str:
    """Load the web console HTML from the bundled template file.

    The template lives at ``brain_alpha_ops/web/index.html``.
    On first call the content is cached in memory.
    """
    global _HTML_CACHE
    if _HTML_CACHE:
        return _HTML_CACHE
    template_path = Path(__file__).resolve().parent / "web" / "index.html"
    if template_path.is_file():
        _HTML_CACHE = template_path.read_text(encoding="utf-8")
    else:
        _HTML_CACHE = "<!doctype html><html><body><h1>Template not found</h1></body></html>"
    return _HTML_CACHE


def _render_html(csrf_token: str, stream_token: str) -> str:
    return (
        _load_html()
        .replace("__BRAIN_ALPHA_OPS_CSRF_TOKEN__", csrf_token)
        .replace("__BRAIN_ALPHA_OPS_STREAM_TOKEN__", stream_token)
    )


def run_config_from_payload(payload: dict) -> RunConfig:
    return _run_config_from_payload(payload, loader=load_run_config)


def config_from_payload(payload: dict):
    return _config_from_payload(payload, loader=load_run_config)


def test_connection(payload: dict) -> dict:
    try:
        run_config = run_config_from_payload(payload)
        api = api_from_run_config(run_config)
        auth_result = api.authenticate()
        if str(run_config.environment).lower() == "production" and hasattr(api, "get_user_profile"):
            api.get_user_profile()
        auth_mode = ""
        if isinstance(auth_result, dict):
            auth_mode = str(auth_result.get("auth") or auth_result.get("environment") or "")
        return {"ok": True, "environment": str(run_config.environment), "auth": auth_mode}
    except Exception as exc:
        return _web_error(exc, "CONNECTION_FAILED")


# B3: Centralized phase label mapping — backend owns all Chinese localization
_PHASE_LABELS: dict[str, str] = {
    "queued": "排队",
    "auth": "认证",
    "scan": "扫描",
    "merge": "合并",
    "startup": "启动",
    "cloud_sync": "云端数据同步",
    "context": "加载上下文",
    "production_loop": "循环生产",
    "local_scoring": "本地评分排序",
    "candidate_pool": "候选池维护",
    "official_validation": "回测前预检",
    "official_simulation": "官方模拟回测",
    "official_deferred": "官方延迟",
    "checking": "批量检查",
    "submitting": "提交",
    "completed": "已完成",
    "stopped": "已停止",
    "failed": "失败",
    "stopping": "正在停止",
    "context_fields": "更新字段缓存",
    "context_operators": "更新算子缓存",
}


def _enrich_progress(progress: dict) -> dict:
    """Add phase_label to any progress dict before sending to frontend."""
    if "phase" in progress and "phase_label" not in progress:
        progress["phase_label"] = _PHASE_LABELS.get(str(progress["phase"]), str(progress["phase"]))
    return progress


class _LegacyInMemoryJobStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}

    def create(self) -> str:
        with self.lock:
            job_id = f"job_{len(self.jobs) + 1:04d}"
            self.jobs[job_id] = {
                "status": "queued",
                "result": None,
                "error": "",
                "cancel": False,
                "updated_at": time.time(),
                "progress": {
                    "phase": "queued",
                    "current": 0,
                    "total": 1,
                    "percent": 0,
                    "message": "任务已排队。",
                    "alpha_id": "",
                },
            }
            return job_id

    def update(self, job_id: str, **kwargs):
        with self.lock:
            if job_id not in self.jobs:
                return
            kwargs.setdefault("updated_at", time.time())
            self.jobs[job_id].update(kwargs)

    def cancel(self, job_id: str):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]["cancel"] = True
                self.jobs[job_id]["status"] = "stopping"
                return True
            return False

    def is_cancelled(self, job_id: str) -> bool:
        with self.lock:
            return bool(self.jobs.get(job_id, {}).get("cancel"))

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            value = self.jobs.get(job_id)
            return dict(value) if value else None

    def latest_active(self) -> tuple[str, dict] | None:
        with self.lock:
            active = [
                (job_id, job)
                for job_id, job in self.jobs.items()
                if job.get("status") in {"queued", "running", "stopping"}
            ]
            if not active:
                return None
            job_id, job = max(active, key=lambda item: float(item[1].get("updated_at", 0.0) or 0.0))
            return job_id, dict(job)

    def latest_any(self) -> tuple[str, dict] | None:
        with self.lock:
            if not self.jobs:
                return None
            job_id, job = max(self.jobs.items(), key=lambda item: float(item[1].get("updated_at", 0.0) or 0.0))
            return job_id, dict(job)


JOBS = DurableJobStore(runtime_project_root() / "data" / "jobs_production.json")
SYNC_JOBS = DurableJobStore(runtime_project_root() / "data" / "jobs_sync.json")
CHECK_JOBS = DurableJobStore(runtime_project_root() / "data" / "jobs_check.json")
SUBMIT_LOCK = threading.Lock()
TASK_EXECUTOR = ThreadTaskExecutor(max_workers=4)
SERVER: ThreadingHTTPServer | None = None
SERVER_STOP = threading.Event()


def active_auxiliary_operation(exclude: str = "", *, allow_production: bool = False) -> tuple[str, str] | None:
    return _active_auxiliary_operation_service(
        production_store=JOBS,
        sync_store=SYNC_JOBS,
        check_store=CHECK_JOBS,
        submit_lock=SUBMIT_LOCK,
        exclude=exclude,
        allow_production=allow_production,
    )


def normalize_host(host: str | None) -> str:
    return _normalize_host_service(host, default_host=HOST)


def _start_thread(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def _submit_background_job(target, *args) -> None:
    TASK_EXECUTOR.submit(target, *args)


def _handler_dispatch_context() -> WebHandlerDispatchContext:
    return WebHandlerDispatchContext(
        route_for=route_for,
        web_error=_web_error,
        payload_truthy=payload_truthy,
        bounded_query_int=_bounded_query_int,
        bounded_query_float=_bounded_query_float,
        get_or_create_session=_get_or_create_session,
        stream_token_for_session=_stream_token_for_session,
        session_cookie_header=_session_cookie_header,
        render_html=_render_html,
        job_status_payload=job_status_payload,
        active_job_payload=active_job_payload,
        lifecycle_payload=lifecycle_payload,
        health_payload=health_payload,
        profile_payload=profile_payload,
        presets_payload=presets_payload,
        jobs=JOBS,
        sync_jobs=SYNC_JOBS,
        check_jobs=CHECK_JOBS,
        enrich_progress=_enrich_progress,
        public_run_config=public_run_config,
        latest_result_snapshot=latest_result_snapshot,
        lifecycle_from_job=lifecycle_from_job,
        cloud_alpha_snapshot=cloud_alpha_snapshot,
        research_memory_snapshot=research_memory_snapshot,
        research_knowledge_snapshot=research_knowledge_snapshot,
        research_observability_snapshot=research_observability_snapshot,
        prompt_run_ledger_snapshot=prompt_run_ledger_snapshot,
        sqlite_index_snapshot=sqlite_index_snapshot,
        sqlite_expression_lookup_payload=sqlite_expression_lookup_payload,
        sqlite_record_lookup_payload=sqlite_record_lookup_payload,
        assistant_context_snapshot=assistant_context_snapshot,
        assistant_guidance_snapshot=assistant_guidance_snapshot,
        assistant_request_snapshot=assistant_request_snapshot,
        anti_overfit_snapshot=anti_overfit_snapshot,
        rolling_validation_snapshot=rolling_validation_snapshot,
        load_check_results=load_check_results,
        user_profile_snapshot=_user_profile_snapshot,
        load_presets=_load_presets,
        connection_test_post_payload=connection_test_post_payload,
        test_connection=test_connection,
        background_job_start_payload=background_job_start_payload,
        start_run_job=lambda job_id, body: _submit_background_job(run_job, job_id, body),
        stop_job_payload=stop_job_payload,
        active_auxiliary_operation=active_auxiliary_operation,
        start_sync_job=lambda job_id, body: _submit_background_job(run_sync_job, job_id, body),
        check_candidate=check_candidate,
        generate_candidates_payload=generate_candidates_payload,
        start_check_batch_job=lambda job_id, body: _submit_background_job(run_check_batch_job, job_id, body),
        submit_lock=SUBMIT_LOCK,
        submit_candidate=submit_candidate,
        submit_batch=submit_batch,
        assistant_response_parse_post_payload=assistant_response_parse_post_payload,
        assistant_response_parse_payload=assistant_response_parse_payload,
        assistant_response_guidance_post_payload=assistant_response_guidance_post_payload,
        assistant_response_guidance_payload=assistant_response_guidance_payload,
        assistant_cross_review_payload=assistant_cross_review_payload,
        save_assistant_guidance_post_payload=save_assistant_guidance_post_payload,
        save_assistant_guidance_payload=save_assistant_guidance_payload,
        session_end_payload=session_end_payload,
        expire_session=_expire_session,
        expired_session_cookie_header=_expired_session_cookie_header,
        start_shutdown=lambda: _start_thread(shutdown_server),
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "BrainAlphaOps/0.1"

    def do_GET(self):
        dispatch_get(self, urlparse(self.path), _handler_dispatch_context())

    def do_POST(self):
        dispatch_post(self, urlparse(self.path), _handler_dispatch_context())

    def log_message(self, _format, *args):
        return

    _MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0:
            raise ValueError("invalid request body length")
        if length > self._MAX_BODY_BYTES:
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _is_allowed_local_request(self) -> bool:
        return _is_allowed_local_request_service(
            host_header=self.headers.get("Host", ""),
            origin_header=self.headers.get("Origin", ""),
            referer_header=self.headers.get("Referer", ""),
            local_hosts=LOCAL_HOSTS,
        )

    def _has_valid_session(self, query_string: str = "") -> bool:
        return SESSION_MANAGER.has_valid_request_session(
            path=urlparse(self.path).path,
            query_string=query_string,
            csrf_header=str(self.headers.get("X-Brain-Alpha-CSRF", "")),
            cookie_header=self.headers.get("Cookie", ""),
        )

    def _session_id_from_cookie(self) -> str:
        return SESSION_MANAGER.session_id_from_cookie(self.headers.get("Cookie", ""))

    def _handle_sse_stream(self, query_string: str):
        """P2: Server-Sent Events endpoint for real-time status updates.

        Replaces the legacy setInterval polling pattern.  The browser
        EventSource API automatically reconnects on disconnect.
        """
        job_id = (parse_qs(query_string).get("job_id") or [""])[0]
        if not job_id:
            self._json({"ok": False, "error_code": "VALIDATION_ERROR", "error": "missing job_id"}, status=400)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

        interval = 1.0  # push interval in seconds
        try:
            while True:
                job = JOBS.get(job_id)
                if not job:
                    self.wfile.write(f"data: {json.dumps({'ok': False, 'error': 'job not found'})}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    break

                payload = {
                    "ok": True,
                    "job_id": job_id,
                    "status": job.get("status", "unknown"),
                    "progress": _enrich_progress(dict(job.get("progress", {}))),
                    "error": job.get("error", ""),
                }
                self.wfile.write(f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8"))
                self.wfile.flush()

                if job.get("status") in ("completed", "stopped", "failed"):
                    break

                time.sleep(interval)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client disconnected — clean exit

    def _html(self, html: str, *, extra_headers: list[tuple[str, str]] | None = None):
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._send_security_headers()
        for name, value in extra_headers or []:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict, status: int = 200, *, extra_headers: list[tuple[str, str]] | None = None):
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._send_security_headers()
        for name, value in extra_headers or []:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )


def run_job(job_id: str, payload: dict):
    if payload.get("guided"):
        run_guided_job_service(
            job_id,
            payload,
            job_store=JOBS,
            run_config_from_payload=run_config_from_payload,
            compute_run_stats=_compute_run_stats,
            safe_error_message=safe_error_message,
            log=logger,
        )
        return
    run_job_service(
        job_id,
        payload,
        job_store=JOBS,
        run_config_from_payload=run_config_from_payload,
        run_pipeline_from_config=run_pipeline_from_config,
        compute_run_stats=_compute_run_stats,
        safe_error_message=safe_error_message,
        log=logger,
    )


def _compute_run_stats(data: dict, run_config) -> dict:
    return _compute_run_stats_service(data, run_config)


def generate_candidates_payload(payload: dict) -> dict:
    return _generate_candidates_payload(payload, run_config_from_payload=run_config_from_payload)


def lifecycle_from_job(job: dict) -> list[dict]:
    return _lifecycle_from_job_service(job, read_storage_jsonl=_read_storage_jsonl, limit=1000)


# C4: Periodic lifecycle file archiving — prevent unbounded growth (>50MB → archive)
_LAST_ARCHIVE_CHECK: float = 0.0
_ARCHIVE_CHECK_INTERVAL: float = 3600.0  # check every hour


def _maybe_archive_lifecycle() -> None:
    """Archive lifecycle.jsonl if > 50MB, throttled to once per hour."""
    global _LAST_ARCHIVE_CHECK
    _LAST_ARCHIVE_CHECK = _maybe_archive_lifecycle_service(
        last_archive_check=_LAST_ARCHIVE_CHECK,
        interval_seconds=_ARCHIVE_CHECK_INTERVAL,
        load_config=load_run_config,
        repository_factory=ResearchRepository,
        safe_error_message=safe_error_message,
        log=logger,
    )


# C2: Settings enum validation — fail fast on invalid values
def _status_category(row: dict) -> str:
    return _status_category_service(row)


def cloud_alpha_snapshot(limit: int = 10000) -> dict:
    return _cloud_alpha_snapshot_service(
        limit=limit,
        load_config=load_run_config,
        runtime_root=runtime_project_root,
        safe_error_message=safe_error_message,
        stale_seconds=CLOUD_SYNC_STALE_SECONDS,
    )


def research_memory_snapshot(*, limit: int = 5000, top_n: int = 10) -> dict:
    return _research_memory_snapshot_service(
        limit=limit,
        top_n=top_n,
        load_config=load_run_config,
        web_error=_web_error,
    )


def research_knowledge_snapshot(*, limit: int = 100, min_confidence: float = 0.0) -> dict:
    return _research_knowledge_snapshot_service(
        limit=limit,
        min_confidence=min_confidence,
        load_config=load_run_config,
        web_error=_web_error,
    )


def research_observability_snapshot(*, limit: int = 5000, top_n: int = 10, include_cloud: bool = True) -> dict:
    return _research_observability_snapshot_service(
        limit=limit,
        top_n=top_n,
        include_cloud=include_cloud,
        load_config=load_run_config,
        durable_job_rows=_durable_job_rows,
        observability_builder=build_research_observability_snapshot,
        web_error=_web_error,
    )


def prompt_run_ledger_snapshot(*, limit: int = 100) -> dict:
    return _prompt_run_ledger_snapshot_service(
        limit=limit,
        load_config=load_run_config,
        web_error=_web_error,
    )


def sqlite_index_snapshot(*, top_n: int = 10) -> dict:
    return _sqlite_index_snapshot_service(
        top_n=top_n,
        load_config=load_run_config,
        web_error=_web_error,
    )


def sqlite_expression_lookup_payload(*, expression: str, top_n: int = 10, min_similarity: float = 0.75) -> dict:
    return _sqlite_expression_lookup_payload_service(
        expression=expression,
        top_n=top_n,
        min_similarity=min_similarity,
        load_config=load_run_config,
        web_error=_web_error,
    )


def sqlite_record_lookup_payload(*, alpha_id: str, limit: int = 50) -> dict:
    return _sqlite_record_lookup_payload_service(
        alpha_id=alpha_id,
        limit=limit,
        load_config=load_run_config,
        web_error=_web_error,
    )


def _durable_job_rows(*, limit: int) -> list[dict]:
    return _durable_job_rows_service(
        stores=[("production_job", JOBS), ("sync_job", SYNC_JOBS), ("check_job", CHECK_JOBS)],
        limit=limit,
    )


def assistant_guidance_snapshot(*, limit: int = 100, min_confidence: float | None = None) -> dict:
    return _assistant_guidance_snapshot_service(
        limit=limit,
        min_confidence=min_confidence,
        load_config=load_run_config,
        bounded_query_float=_bounded_query_float,
        payload_truthy=payload_truthy,
        read_storage_jsonl=_read_storage_jsonl,
        web_error=_web_error,
    )


def _assistant_guidance_history(
    rows: list[dict],
    *,
    min_confidence: float,
    scoring_policy: dict | None = None,
    outcomes_by_guidance: dict[str, dict] | None = None,
) -> list[dict]:
    return _assistant_guidance_history_service(
        rows,
        min_confidence=min_confidence,
        scoring_policy=scoring_policy,
        outcomes_by_guidance=outcomes_by_guidance,
        bounded_query_float=_bounded_query_float,
        payload_truthy=payload_truthy,
    )


def _assistant_guidance_outcome_status(row: dict) -> str:
    return assistant_guidance_outcome_status(row)


def _int_from_any(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float_from_any(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def assistant_context_snapshot(
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_prompt: bool = True,
    include_sensitive: bool = False,
) -> dict:
    return _assistant_context_snapshot_service(
        limit=limit,
        top_n=top_n,
        include_prompt=include_prompt,
        include_sensitive=include_sensitive,
        load_config=load_run_config,
        latest_result_snapshot=latest_result_snapshot,
        cloud_alpha_snapshot=cloud_alpha_snapshot,
        web_error=_web_error,
    )


def assistant_request_snapshot(
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_prompt: bool = True,
    include_offline_draft: bool = True,
    include_sensitive: bool = False,
) -> dict:
    return _assistant_request_snapshot_service(
        limit=limit,
        top_n=top_n,
        include_prompt=include_prompt,
        include_offline_draft=include_offline_draft,
        include_sensitive=include_sensitive,
        assistant_context_snapshot=assistant_context_snapshot,
        web_error=_web_error,
    )


def assistant_response_parse_payload(payload: dict) -> dict:
    return _assistant_response_parse_payload_service(payload)


def assistant_response_guidance_payload(payload: dict) -> dict:
    return _assistant_response_guidance_payload_service(payload, bounded_query_float=_bounded_query_float)


def anti_overfit_snapshot(candidate_id: str = "") -> dict:
    return _anti_overfit_snapshot_service(
        candidate_id=candidate_id,
        latest_result_snapshot=latest_result_snapshot,
    )


def rolling_validation_snapshot(candidate_id: str = "", windows: int = 4) -> dict:
    return _rolling_validation_snapshot_service(
        candidate_id=candidate_id,
        windows=windows,
        latest_result_snapshot=latest_result_snapshot,
    )


def assistant_cross_review_payload(payload: dict) -> dict:
    return _assistant_cross_review_payload_service(
        payload,
        bounded_query_float=_bounded_query_float,
    )


def save_assistant_guidance_payload(payload: dict) -> dict:
    return _save_assistant_guidance_payload_service(
        payload,
        run_config_from_payload=run_config_from_payload,
        bounded_query_float=_bounded_query_float,
        payload_truthy=payload_truthy,
        assistant_guidance_snapshot=assistant_guidance_snapshot,
        repository_factory=ResearchRepository,
    )


def latest_result_snapshot() -> dict:
    return _latest_result_snapshot_service(
        job_store=JOBS,
        latest_run_history_path=_latest_run_history_path,
        enrich_progress=_enrich_progress,
        web_error=_web_error,
    )

def _latest_run_history_path() -> Path | None:
    return _latest_run_history_path_service(load_config=load_run_config)

def _user_profile_snapshot() -> dict:
    return _user_profile_snapshot_service(
        job_store=JOBS,
        storage_jsonl_path=_storage_jsonl_path,
        safe_error_message=safe_error_message,
    )

# D1: Preset configuration — single source of truth for market presets
def _load_presets() -> dict:
    return _load_presets_service(runtime_root=runtime_project_root, log=logger)


def _match_preset_id(settings: dict) -> str:
    return _match_preset_id_service(settings, _load_presets())


def _dedupe_cloud_alpha_rows(rows: list[dict]) -> list[dict]:
    return _dedupe_cloud_alpha_rows_service(rows)


def _latest_cached_user_alphas(limit: int = 10000) -> list[dict]:
    return _latest_cached_user_alphas_service(limit=limit, load_config=load_run_config)


def _latest_cached_user_alpha_path() -> Path | None:
    return _latest_cached_user_alpha_path_service(load_config=load_run_config)


def _cached_user_alpha_paths() -> list[Path]:
    from brain_alpha_ops.web_cloud_snapshot import cached_user_alpha_paths

    return cached_user_alpha_paths(load_config=load_run_config)


def _path_modified_at(path: Path | None) -> tuple[str, int | None]:
    return _path_modified_at_service(path)


def _extract_alpha_rows(data) -> list[dict]:
    from brain_alpha_ops.web_cloud_snapshot import extract_alpha_rows

    return extract_alpha_rows(data)


def _official_context_file_counts() -> dict[str, int]:
    return _official_context_file_counts_service(
        load_config=load_run_config,
        runtime_root=runtime_project_root,
        safe_error_message=safe_error_message,
    )


def _read_official_context_metadata(filename: str) -> dict:
    from brain_alpha_ops.web_cloud_snapshot import read_official_context_metadata

    return read_official_context_metadata(
        filename,
        load_config=load_run_config,
        runtime_root=runtime_project_root,
        safe_error_message=safe_error_message,
    )


def _read_official_context_json(filename: str) -> list[dict]:
    return _read_official_context_json_service(
        filename,
        load_config=load_run_config,
        runtime_root=runtime_project_root,
        safe_error_message=safe_error_message,
    )


def _cloud_alpha_summary(rows: list[dict]) -> dict:
    return _cloud_alpha_summary_service(
        rows,
        load_config=load_run_config,
        runtime_root=runtime_project_root,
        safe_error_message=safe_error_message,
    )


def _drop_mock_rows_if_real(rows: list[dict]) -> list[dict]:
    return _drop_mock_rows_if_real_service(rows)


def _cloud_alpha_id(row: dict) -> str:
    from brain_alpha_ops.web_cloud_snapshot import cloud_alpha_id

    return cloud_alpha_id(row)


def _cloud_row_sort_key(row: dict) -> str:
    from brain_alpha_ops.web_cloud_snapshot import cloud_row_sort_key

    return cloud_row_sort_key(row)


def candidate_from_payload(payload: dict) -> dict:
    return _candidate_from_payload(payload, JOBS)


def sync_cloud_alphas(payload: dict) -> dict:
    return sync_cloud_alphas_payload(
        payload,
        run_config_from_payload=run_config_from_payload,
        api_from_run_config=api_from_run_config,
        repository_factory=ResearchRepository,
        datasets_from_fields=_datasets_from_fields,
        persist_official_context=_persist_official_context,
        default_fields=list(DEFAULT_FIELDS),
        default_operators=list(DEFAULT_OPERATORS),
    )


def run_sync_job(job_id: str, payload: dict):
    return run_sync_job_service(
        job_id,
        payload,
        store=SYNC_JOBS,
        run_config_from_payload=run_config_from_payload,
        api_from_run_config=api_from_run_config,
        repository_factory=ResearchRepository,
        datasets_from_fields=_datasets_from_fields,
        persist_official_context=_persist_official_context,
        default_fields=list(DEFAULT_FIELDS),
        default_operators=list(DEFAULT_OPERATORS),
        safe_error_message=safe_error_message,
        error_payload=error_payload,
    )


def run_check_batch_job(job_id: str, payload: dict):
    return run_check_batch_job_service(
        job_id,
        payload,
        store=CHECK_JOBS,
        passed_candidates_from_payload=passed_candidates_from_payload,
        run_config_from_payload=run_config_from_payload,
        api_from_run_config=api_from_run_config,
        repository_factory=ResearchRepository,
        ledger_factory=SubmissionLedger,
        refresh_cloud_context_for_check=refresh_cloud_context_for_check,
        payload_truthy=payload_truthy,
        check_candidate_availability=check_candidate_availability,
        observability_submission_preflight=observability_submission_preflight,
        safe_error_message=safe_error_message,
        error_payload=error_payload,
    )


def refresh_cloud_context_for_check(
    api,
    repo: ResearchRepository,
    sync_range: str,
    job_id: str,
    total: int,
    mode: str,
    region: str = "",
    *,
    refresh_remote: bool = False,
) -> tuple[list[dict], str]:
    """Refresh cloud alphas AND fields/operators context for batch check.

    Returns (cloud_alphas, context_error). context_error is empty on success,
    or a human-readable message describing what failed during context refresh.

    P0-2 修复: fields/operators 拉取结果不再丢弃，异常不再静默忽略。
    """
    return refresh_cloud_context_for_check_service(
        api,
        repo,
        sync_range,
        job_id,
        total,
        mode,
        region,
        refresh_remote=refresh_remote,
        store=CHECK_JOBS,
        official_context_file_counts=_official_context_file_counts,
        datasets_from_fields=_datasets_from_fields,
        persist_official_context=_persist_official_context,
        safe_error_message=safe_error_message,
    )


def _datasets_from_fields(fields: list[dict]) -> list[dict]:
    return _datasets_from_fields_service(
        fields,
        load_config=load_run_config,
        runtime_root=runtime_project_root,
        safe_error_message=safe_error_message,
    )


def _persist_official_context(fields: list[dict], operators: list[dict], datasets: list[dict]) -> None:
    _persist_official_context_service(
        fields,
        operators,
        datasets,
        load_config=load_run_config,
        runtime_root=runtime_project_root,
        safe_error_message=safe_error_message,
    )


def _save_official_context_json(filename: str, items: list[dict]) -> None:
    _save_official_context_json_service(
        filename,
        items,
        load_config=load_run_config,
        runtime_root=runtime_project_root,
    )


def passed_candidates_from_payload(payload: dict) -> list[dict]:
    return _passed_candidates_from_payload(payload, JOBS)


def check_candidate_availability(
    candidate: dict,
    mode: str,
    api,
    ledger: SubmissionLedger,
    cloud_alphas: list[dict],
    cloud_error: str = "",
    observability_preflight: dict | None = None,
) -> dict:
    return _check_candidate_availability(
        candidate,
        mode,
        api,
        ledger,
        cloud_alphas,
        cloud_error,
        observability_preflight,
        safe_error_message=safe_error_message,
        observability_submission_preflight=observability_submission_preflight,
    )


def cloud_status_for(candidate: dict, cloud_alphas: list[dict]) -> dict:
    return _cloud_status_for(candidate, cloud_alphas)


def cloud_similarity_risk(candidate: dict, cloud_alphas: list[dict]) -> dict:
    return _cloud_similarity_risk(candidate, cloud_alphas)


def check_candidate(payload: dict) -> dict:
    """Single Alpha pre-submit check — called by POST /api/check.

    Uses check_candidate_availability for the full 8-check suite (label_cn,
    suggestion, cloud context), then persists the result.
    """
    return check_candidate_payload(
        payload,
        candidate_from_payload=candidate_from_payload,
        run_config_from_payload=run_config_from_payload,
        api_from_run_config=api_from_run_config,
        repository_factory=ResearchRepository,
        ledger_factory=SubmissionLedger,
        refresh_cloud_context_for_check=refresh_cloud_context_for_check,
        payload_truthy=payload_truthy,
        check_candidate_availability=check_candidate_availability,
        observability_submission_preflight=observability_submission_preflight,
        web_error=_web_error,
    )


def submission_preflight_error(candidate: dict, run_config: RunConfig) -> str:
    official_id = official_alpha_id(candidate)
    if not official_id:
        return "缺少官方 Alpha ID，请先完成官方回测。"
    if str(run_config.environment).lower() == "production":
        mock_reasons = mock_source_reasons(candidate)
        if mock_reasons:
            return "Production submit blocked non-production mock/demo/test candidate: " + "; ".join(mock_reasons)
    gate = candidate.get("gate") or {}
    if not (gate.get("submission_ready") or candidate.get("lifecycle_status") == "submission_ready"):
        return "该 Alpha 尚未达到可提交状态，请先在达标列表完成检查。"
    status_text = f"{candidate.get('lifecycle_status', '')} {gate.get('status', '')}".lower()
    if any(word in status_text for word in ("failed", "rejected", "不达标")):
        return "该 Alpha 已标记为失败或不达标，不能提交。"

    ledger = SubmissionLedger(run_config.ops.storage_dir)
    records = ledger.records()
    candidate_expr_key = expression_key(str(candidate.get("expression", "")))
    duplicate_id = any(str(row.get("official_alpha_id") or "") == official_id for row in records)
    duplicate_expr = bool(candidate_expr_key) and any(expression_key(str(row.get("expression", ""))) == candidate_expr_key for row in records)
    if duplicate_id:
        return "本地提交记录中已存在该官方 Alpha ID。"
    if duplicate_expr:
        return "本地提交记录中已存在相同表达式。"

    cloud_snapshot = cloud_alpha_snapshot(limit=2000)
    cloud_rows = cloud_snapshot.get("alphas") or []
    cloud_summary = cloud_snapshot.get("summary") or {}
    if run_config.ops.budget.require_cloud_sync:
        if not cloud_rows:
            return "提交前请先同步云端数据。"
        if cloud_summary.get("is_stale"):
            return "云端数据已超过 24 小时未刷新，请先同步云端数据。"

    cloud_status = cloud_status_for(candidate, cloud_rows)
    if str(cloud_status.get("status", "")).upper() in {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}:
        return "云端缓存显示该 Alpha 已提交。"
    return ""


def _submit_preflight_block(error_code: str, error: str, *, category: str = "validation", action: str = "") -> dict:
    return _submission_preflight_block_service(error_code, error, category=category, action=action)


def submission_preflight_advisory(candidate: dict, run_config: RunConfig) -> dict:
    return _submission_preflight_advisory(
        candidate,
        run_config,
        ledger_factory=SubmissionLedger,
        cloud_alpha_snapshot=cloud_alpha_snapshot,
        cloud_status_for=cloud_status_for,
    )


def observability_submission_preflight(storage_dir: str, *, limit: int = 5000, top_n: int = 5) -> dict:
    return _observability_submission_preflight(
        storage_dir,
        limit=limit,
        top_n=top_n,
        observability_builder=build_research_observability_snapshot,
        safe_error_message=safe_error_message,
    )


def _compact_expression(value: object) -> str:
    return " ".join(str(value or "").split())


def cloud_row_expression(row: dict) -> str:
    return _cloud_row_expression(row)


def record_submit_blocked(payload: dict, candidate: dict, run_config: RunConfig, failure_reason: str):
    try:
        official_id = official_alpha_id(candidate)
        ResearchRepository(run_config.ops.storage_dir).save_lifecycle_record(
            str(payload.get("job_id", "")) or "manual_submit",
            {
                "timestamp": utc_now(),
                "alpha_id": candidate.get("alpha_id", ""),
                "official_alpha_id": official_id,
                "simulation_id": candidate.get("simulation_id", ""),
                "stage": "submission_blocked",
                "status": "BLOCKED",
                "family": candidate.get("family", ""),
                "score": (candidate.get("scorecard") or {}).get("total_score", 0.0),
                "expression": candidate.get("expression", ""),
                "submit_trigger": str(payload.get("submit_mode", "manual")),
                "environment": str(run_config.environment),
                "failure_reason": failure_reason,
                "note": failure_reason,
            },
        )
    except Exception:
        logger.warning(
            "failed to record submission blocked for alpha_id=%s reason=%s",
            candidate.get("alpha_id", "?"), failure_reason, exc_info=True,
        )


def submit_candidate(payload: dict) -> dict:
    return submit_candidate_payload(
        payload,
        candidate_from_payload=candidate_from_payload,
        run_config_from_payload=run_config_from_payload,
        submission_preflight_advisory=submission_preflight_advisory,
        record_submit_blocked=record_submit_blocked,
        official_alpha_id=official_alpha_id,
        observability_submission_preflight=observability_submission_preflight,
        payload_truthy=payload_truthy,
        api_from_run_config=api_from_run_config,
    )


def load_check_results() -> dict:
    return _load_check_results_service(
        read_storage_jsonl=_read_storage_jsonl,
        safe_error_message=safe_error_message,
        log=logger,
        limit=5000,
    )


def submit_batch(payload: dict) -> dict:
    return submit_batch_payload(
        payload,
        run_config_from_payload=run_config_from_payload,
        observability_submission_preflight=observability_submission_preflight,
        submit_candidate=submit_candidate,
        candidate_from_payload=candidate_from_payload,
        web_error=_web_error,
        payload_truthy=payload_truthy,
    )


def _storage_jsonl_path(filename: str) -> Path:
    return _storage_jsonl_path_service(filename, load_config=load_run_config)


def _read_storage_jsonl(filename: str, *, limit: int = 500) -> list[dict]:
    return _read_storage_jsonl_service(filename, limit=limit, load_config=load_run_config)


def _read_storage_jsonl_stats(filename: str, *, limit: int = 500) -> dict:
    return _read_storage_jsonl_stats_service(filename, limit=limit, load_config=load_run_config)


def _tail_text_lines(path: Path, limit: int, *, chunk_size: int = 1024 * 1024) -> list[str]:
    return tail_text_lines(path, limit, chunk_size=chunk_size)


def public_run_config() -> dict:
    config = load_run_config().to_dict()
    credentials = config.get("credentials", {})
    config["credentials"] = {
        "username": "",
        "password": "",
        "token": "",
        "username_env": credentials.get("username_env", "BRAIN_USERNAME"),
        "password_env": credentials.get("password_env", "BRAIN_PASSWORD"),
        "token_env": credentials.get("token_env", "BRAIN_TOKEN"),
    }
    return config


def find_free_port(start: int = DEFAULT_PORT, host: str = HOST) -> int:
    return _find_free_port_service(start, host=host)


def shutdown_server():
    _shutdown_server_service(SERVER, SERVER_STOP)


def serve(
    port: int | None = None,
    open_browser: bool = True,
    host: str = HOST,
    session_ttl_seconds: int | None = None,
    allow_multiple_sessions: bool | None = None,
    allow_remote: bool = False,
) -> str:
    global SERVER
    url, SERVER = _serve_service(
        port=port,
        open_browser=open_browser,
        host=host,
        default_port=DEFAULT_PORT,
        handler_class=Handler,
        stop_event=SERVER_STOP,
        configure_session_policy=configure_session_policy,
        normalize_host=normalize_host,
        loopback_bind_hosts=LOOPBACK_BIND_HOSTS,
        allow_remote=allow_remote,
        session_ttl_seconds=session_ttl_seconds,
        allow_multiple_sessions=allow_multiple_sessions,
    )
    return url


def smoke_test_server(port: int | None = None) -> dict:
    """Exercise the local HTTP session lifecycle without opening a browser."""
    return _smoke_test_server_service(
        port=port,
        default_port=DEFAULT_PORT,
        serve_func=serve,
        shutdown_func=shutdown_server,
        parse_cookies=_parse_cookies,
        cookie_name=SESSION_COOKIE_NAME,
        csrf_for_session=_csrf_for_session,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    import time

    def safe_print(message: str) -> None:
        stream = getattr(sys, "stdout", None)
        if stream is None:
            return
        try:
            print(message)
        except Exception:
            return

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args(argv)
    run_config = load_run_config(args.config or None)
    if args.smoke_test:
        config_from_payload({"environment": "mock"})
        result = smoke_test_server(port=args.port or run_config.web.port)
        safe_print(json.dumps({"ok": True, "status": "web ready", **result}, ensure_ascii=False))
        return 0
    url = serve(
        port=args.port or run_config.web.port,
        open_browser=run_config.web.open_browser and not args.no_browser,
        host=run_config.web.host,
        session_ttl_seconds=run_config.web.session_ttl_seconds,
        allow_multiple_sessions=run_config.web.allow_multiple_sessions,
        allow_remote=run_config.web.allow_remote,
    )
    safe_print("BRAIN Alpha Ops 已启动")
    safe_print(f"访问地址：{url}")
    safe_print("关闭此窗口或按 Ctrl+C 可停止本地服务。")
    try:
        while not SERVER_STOP.wait(3600):
            pass
    except KeyboardInterrupt:
        shutdown_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
