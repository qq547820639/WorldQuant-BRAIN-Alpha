"""Tiny local web console for BRAIN Alpha Ops.

The server uses only Python's standard library. It is intentionally local-only
and keeps credentials in memory for the current request.
"""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import logging
import sys
import threading

logger = logging.getLogger(__name__)

from brain_alpha_ops.config import (
    RunConfig as _RunConfig,
    load_run_config as _load_run_config,
    runtime_project_root as _runtime_project_root,
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
    payload_truthy as _payload_truthy,
    run_config_from_payload as _run_config_from_payload,
    save_run_config_payload as _save_run_config_payload,
)
from brain_alpha_ops.web_config_schema import public_config_schema as _public_config_schema
from brain_alpha_ops import web_html as _web_html
from brain_alpha_ops import web_runtime_facade as _runtime_facade
from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS as _DEFAULT_FIELDS, DEFAULT_OPERATORS as _DEFAULT_OPERATORS
from brain_alpha_ops.jsonl import tail_text_lines as _tail_text_lines_service
from brain_alpha_ops.observability import error_payload as _error_payload
from brain_alpha_ops.task_executor import ThreadTaskExecutor as _ThreadTaskExecutor
from brain_alpha_ops.research.observability import build_research_observability_snapshot as _build_research_observability_snapshot
from brain_alpha_ops.research.repository import ResearchRepository as _ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger as _SubmissionLedger
from brain_alpha_ops.runner import api_from_run_config as _api_from_run_config, run_pipeline_from_config as _run_pipeline_from_config
from brain_alpha_ops.tasks import JobStore as _DurableJobStore
from brain_alpha_ops.web_check_availability import (
    check_candidate_availability as _check_candidate_availability,
    cloud_row_expression as _cloud_row_expression,
    cloud_similarity_risk as _cloud_similarity_risk,
    cloud_status_for as _cloud_status_for,
)
from brain_alpha_ops.web_check_batch_job import run_check_batch_job_service as _run_check_batch_job_service
from brain_alpha_ops.web_cloud_snapshot import (
    cached_user_alpha_paths as _cached_user_alpha_paths_service,
    cloud_alpha_snapshot as _cloud_alpha_snapshot_service,
    cloud_alpha_summary as _cloud_alpha_summary_service,
    cloud_alpha_id as _cloud_alpha_id_service,
    cloud_row_sort_key as _cloud_row_sort_key_service,
    datasets_from_fields as _datasets_from_fields_service,
    dedupe_cloud_alpha_rows as _dedupe_cloud_alpha_rows_service,
    extract_alpha_rows as _extract_alpha_rows_service,
    latest_cached_user_alpha_path as _latest_cached_user_alpha_path_service,
    latest_cached_user_alphas as _latest_cached_user_alphas_service,
    official_context_file_counts as _official_context_file_counts_service,
    path_modified_at as _path_modified_at_service,
    persist_official_context as _persist_official_context_service,
    read_official_context_metadata as _read_official_context_metadata_service,
    read_official_context_json as _read_official_context_json_service,
    read_storage_jsonl as _read_storage_jsonl_service,
    read_storage_jsonl_stats as _read_storage_jsonl_stats_service,
    save_official_context_json as _save_official_context_json_service,
    storage_jsonl_path as _storage_jsonl_path_service,
)
from brain_alpha_ops.web_candidate_check import check_candidate_payload as _check_candidate_payload
from brain_alpha_ops.web_candidate_generation import generate_candidates_payload as _generate_candidates_payload
from brain_alpha_ops.web_candidate_selection import (
    candidate_from_payload as _candidate_from_payload,
    candidate_official_metrics as _candidate_official_metrics,
    is_passed_candidate_for_check as _is_passed_candidate_for_check,
    official_alpha_id as _official_alpha_id,
    passed_candidates_from_payload as _passed_candidates_from_payload,
)
from brain_alpha_ops.web_cloud_context_refresh import refresh_cloud_context_for_check_service as _refresh_cloud_context_for_check_service
from brain_alpha_ops.web_get_handlers import (
    active_job_payload as _active_job_payload,
    health_payload as _health_payload,
    job_status_payload as _job_status_payload,
    lifecycle_payload as _lifecycle_payload,
    presets_payload as _presets_payload,
    profile_payload as _profile_payload,
)
from brain_alpha_ops.web_post_handlers import (
    assistant_response_guidance_post_payload as _assistant_response_guidance_post_payload,
    assistant_response_parse_post_payload as _assistant_response_parse_post_payload,
    background_job_start_payload as _background_job_start_payload,
    connection_test_post_payload as _connection_test_post_payload,
    save_assistant_guidance_post_payload as _save_assistant_guidance_post_payload,
    session_end_payload as _session_end_payload,
    stop_job_payload as _stop_job_payload,
)
from brain_alpha_ops.web_rate_limit import RequestRateLimiter as _RequestRateLimiter
from brain_alpha_ops.web_handler_dispatch import (
    WebDispatchActionContext as _WebDispatchActionContext,
    WebDispatchAssistantContext as _WebDispatchAssistantContext,
    WebDispatchConfigContext as _WebDispatchConfigContext,
    WebDispatchCoreContext as _WebDispatchCoreContext,
    WebDispatchJobContext as _WebDispatchJobContext,
    WebDispatchResearchContext as _WebDispatchResearchContext,
    WebDispatchSessionContext as _WebDispatchSessionContext,
    WebHandlerDispatchContext as _WebHandlerDispatchContext,
    dispatch_get as _dispatch_get,
    dispatch_post as _dispatch_post,
)
from brain_alpha_ops.web_http_handler import create_handler_class as _create_handler_class
from brain_alpha_ops.web_routes import route_for as _route_for
from brain_alpha_ops.web_async_jobs import progress_update as _progress_update, run_simple_async_job_service as _run_simple_async_job_service
from brain_alpha_ops.web_run_job import run_guided_job_service as _run_guided_job_service, run_job_service as _run_job_service
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
from brain_alpha_ops.web_errors import (
    safe_error_message as _safe_error_message_service,
    safe_error_payload as _safe_error_payload_service,
    web_error_payload as _web_error_payload_service,
)
from brain_alpha_ops.web_progress import enrich_progress as _enrich_progress_service
from brain_alpha_ops.web_server_lifecycle import (
    find_free_port as _find_free_port_service,
    serve as _serve_service,
    shutdown_server as _shutdown_server_service,
    smoke_test_server as _smoke_test_server_service,
)
from brain_alpha_ops import web_session as _web_session
from brain_alpha_ops.web_snapshot_facade import WebSnapshotFacade as _WebSnapshotFacade
from brain_alpha_ops.web_snapshot_runtime import WebSnapshotRuntime as _WebSnapshotRuntime
from brain_alpha_ops.web_security import (
    DEFAULT_SESSION_TTL_SECONDS as _DEFAULT_SESSION_TTL_SECONDS,
    LOOPBACK_BIND_HOSTS as _LOOPBACK_BIND_HOSTS,
    SESSION_COOKIE_NAME as _SESSION_COOKIE_NAME,
    header_hostname as _header_hostname_service,
    header_port as _header_port_service,
    parse_cookies as _parse_cookies_service,
    path_requires_session as _path_requires_session_service,
)
from brain_alpha_ops.web_sqlite_indexes import (
    sqlite_expression_lookup_payload as _sqlite_expression_lookup_payload_service,
    sqlite_index_snapshot as _sqlite_index_snapshot_service,
    sqlite_record_lookup_payload as _sqlite_record_lookup_payload_service,
)
from brain_alpha_ops.web_submission_batch import submit_batch_payload as _submit_batch_payload
from brain_alpha_ops.web_submission_single import submit_candidate_payload as _submit_candidate_payload
from brain_alpha_ops.web_submission_safety import (
    observability_submission_preflight as _observability_submission_preflight,
    record_submit_blocked_event as _record_submit_blocked_event,
    submission_preflight_advisory as _submission_preflight_advisory,
    submission_preflight_error_message as _submission_preflight_error_message,
    submit_preflight_block as _submission_preflight_block_service,
)
from brain_alpha_ops.web_sync_job import run_sync_job_service as _run_sync_job_service
from brain_alpha_ops.web_sync_payload import sync_cloud_alphas_payload as _sync_cloud_alphas_payload


# ── Runtime constants (centralized in runtime_constants.py) ──
from brain_alpha_ops.runtime_constants import CloudDefaults as _CloudDefaults, WebDefaults as _WebDefaults, SnapshotDefaults as _SnapshotDefaults

HOST = _WebDefaults.HOST
DEFAULT_PORT = _WebDefaults.PORT
CLOUD_SYNC_STALE_SECONDS = _CloudDefaults.CLOUD_SYNC_STALE_SECONDS
SESSION_TTL_SECONDS = _DEFAULT_SESSION_TTL_SECONDS
SESSION_ALLOW_MULTIPLE = True
SESSION_MANAGER = _web_session.SESSION_MANAGER
SESSIONS = _web_session.SESSIONS
SESSION_LOCK = _web_session.SESSION_LOCK

# Allowed base URLs per environment — used to prevent SSRF via frontend.
HTML = _HTML_CACHE = ""


class WebApplicationContext:
    """Runtime context facade for web console services.

    The public module still owns the mutable stores for compatibility, but
    runtime helpers now receive a named context object instead of looking up the
    module through ``sys.modules[__name__]`` at every call site.
    """

    def __init__(self, module):
        self._module = module

    def __getattr__(self, name: str):
        return getattr(self._module, name)


WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])


def web_application_context() -> WebApplicationContext:
    return WEB_APPLICATION_CONTEXT


def _app_context() -> WebApplicationContext:
    return WEB_APPLICATION_CONTEXT


_LEGACY_IMPORTED_EXPORTS = {
    "RunConfig": _RunConfig,
    "load_run_config": _load_run_config,
    "runtime_project_root": _runtime_project_root,
    "payload_truthy": _payload_truthy,
    "public_config_schema": _public_config_schema,
    "web_html": _web_html,
    "DEFAULT_FIELDS": _DEFAULT_FIELDS,
    "DEFAULT_OPERATORS": _DEFAULT_OPERATORS,
    "tail_text_lines": _tail_text_lines_service,
    "error_payload": _error_payload,
    "ThreadTaskExecutor": _ThreadTaskExecutor,
    "build_research_observability_snapshot": _build_research_observability_snapshot,
    "ResearchRepository": _ResearchRepository,
    "SubmissionLedger": _SubmissionLedger,
    "api_from_run_config": _api_from_run_config,
    "run_pipeline_from_config": _run_pipeline_from_config,
    "DurableJobStore": _DurableJobStore,
    "run_check_batch_job_service": _run_check_batch_job_service,
    "check_candidate_payload": _check_candidate_payload,
    "candidate_official_metrics": _candidate_official_metrics,
    "is_passed_candidate_for_check": _is_passed_candidate_for_check,
    "official_alpha_id": _official_alpha_id,
    "refresh_cloud_context_for_check_service": _refresh_cloud_context_for_check_service,
    "active_job_payload": _active_job_payload,
    "health_payload": _health_payload,
    "job_status_payload": _job_status_payload,
    "lifecycle_payload": _lifecycle_payload,
    "presets_payload": _presets_payload,
    "profile_payload": _profile_payload,
    "assistant_response_guidance_post_payload": _assistant_response_guidance_post_payload,
    "assistant_response_parse_post_payload": _assistant_response_parse_post_payload,
    "background_job_start_payload": _background_job_start_payload,
    "connection_test_post_payload": _connection_test_post_payload,
    "save_assistant_guidance_post_payload": _save_assistant_guidance_post_payload,
    "session_end_payload": _session_end_payload,
    "stop_job_payload": _stop_job_payload,
    "RequestRateLimiter": _RequestRateLimiter,
    "WebDispatchActionContext": _WebDispatchActionContext,
    "WebDispatchAssistantContext": _WebDispatchAssistantContext,
    "WebDispatchConfigContext": _WebDispatchConfigContext,
    "WebDispatchCoreContext": _WebDispatchCoreContext,
    "WebDispatchJobContext": _WebDispatchJobContext,
    "WebDispatchResearchContext": _WebDispatchResearchContext,
    "WebDispatchSessionContext": _WebDispatchSessionContext,
    "WebHandlerDispatchContext": _WebHandlerDispatchContext,
    "dispatch_get": _dispatch_get,
    "dispatch_post": _dispatch_post,
    "create_handler_class": _create_handler_class,
    "route_for": _route_for,
    "progress_update": _progress_update,
    "run_simple_async_job_service": _run_simple_async_job_service,
    "run_guided_job_service": _run_guided_job_service,
    "run_job_service": _run_job_service,
    "web_session": _web_session,
    "WebSnapshotFacade": _WebSnapshotFacade,
    "WebSnapshotRuntime": _WebSnapshotRuntime,
    "DEFAULT_SESSION_TTL_SECONDS": _DEFAULT_SESSION_TTL_SECONDS,
    "LOOPBACK_BIND_HOSTS": _LOOPBACK_BIND_HOSTS,
    "SESSION_COOKIE_NAME": _SESSION_COOKIE_NAME,
    "submit_batch_payload": _submit_batch_payload,
    "submit_candidate_payload": _submit_candidate_payload,
    "run_sync_job_service": _run_sync_job_service,
    "sync_cloud_alphas_payload": _sync_cloud_alphas_payload,
    "CloudDefaults": _CloudDefaults,
    "WebDefaults": _WebDefaults,
    "SnapshotDefaults": _SnapshotDefaults,
}


def __getattr__(name: str):
    try:
        return _LEGACY_IMPORTED_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc


def _load_run_config_provider():
    return globals().get("load_run_config", _load_run_config)


def _runtime_project_root_provider():
    return globals().get("runtime_project_root", _runtime_project_root)


_header_hostname = _header_hostname_service
_header_port = _header_port_service
_path_requires_session = _path_requires_session_service


def configure_session_policy(
    ttl_seconds: int | float | None = None,
    allow_multiple_sessions: bool | None = None,
    secure_cookies: bool | None = None,
) -> None:
    global SESSION_TTL_SECONDS, SESSION_ALLOW_MULTIPLE
    _web_session.configure_session_policy(ttl_seconds, allow_multiple_sessions, secure_cookies)
    SESSION_TTL_SECONDS = _web_session.session_ttl_seconds()
    SESSION_ALLOW_MULTIPLE = _web_session.session_allow_multiple()


_parse_cookies = _parse_cookies_service
_session_cookie_header = _web_session.session_cookie_header
_expired_session_cookie_header = _web_session.expired_session_cookie_header
_prune_sessions = _web_session.prune_sessions
_create_session = _web_session.create_session
_expire_session = _web_session.expire_session
_validate_session_token = _web_session.validate_session_token
_validate_session = _web_session.validate_session
_validate_stream_session = _web_session.validate_stream_session
_csrf_for_session = _web_session.csrf_for_session
_stream_token_for_session = _web_session.stream_token_for_session
_get_or_create_session = _web_session.get_or_create_session
_remote_admin_required = _web_session.remote_admin_required
_has_valid_admin_token = _web_session.has_valid_admin_token

safe_error_message = _safe_error_message_service
safe_error_payload = _safe_error_payload_service
_web_error = _web_error_payload_service
_load_html = _web_html.load_html
_render_html = _web_html.render_html
_script_hash_sources = _web_html.script_hash_sources
_style_hash_sources = _web_html.style_hash_sources
content_security_policy_for_html = _web_html.content_security_policy_for_html

def run_config_from_payload(payload):
    return _run_config_from_payload(payload, loader=_load_run_config_provider())
def config_from_payload(payload):
    return _config_from_payload(payload, loader=_load_run_config_provider())
def save_run_config_payload(payload):
    return _save_run_config_payload(payload, loader=_load_run_config_provider())


def test_connection(payload):
    return _runtime_facade.test_connection(_app_context(), payload)


_enrich_progress = _enrich_progress_service


JOBS = _DurableJobStore(_runtime_project_root() / "data" / "jobs_production.json")
SYNC_JOBS = _DurableJobStore(_runtime_project_root() / "data" / "jobs_sync.json", job_prefix="sync")
CHECK_JOBS = _DurableJobStore(_runtime_project_root() / "data" / "jobs_check.json", job_prefix="check")
ASYNC_JOBS = _DurableJobStore(_runtime_project_root() / "data" / "jobs_async.json", job_prefix="task")
SUBMIT_LOCK = threading.Lock()
RATE_LIMITER = _RequestRateLimiter()
TASK_EXECUTOR = _ThreadTaskExecutor(max_workers=4)
SERVER: ThreadingHTTPServer | None = None
SERVER_STOP = threading.Event()


def active_auxiliary_operation(exclude='', allow_production=False):
    return _active_auxiliary_operation_service(production_store=JOBS, sync_store=SYNC_JOBS, check_store=CHECK_JOBS, submit_lock=SUBMIT_LOCK, exclude=exclude, allow_production=allow_production)
def rate_limit_request(key, method, path):
    return RATE_LIMITER.check(key=key, method=method, path=path)


def normalize_host(host: str | None) -> str:
    return _web_session.normalize_host(host, default_host=HOST)


def _start_thread(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def _submit_background_job(target, *args) -> None:
    TASK_EXECUTOR.submit(target, *args)


def _handler_dispatch_context():
    return _runtime_facade.handler_dispatch_context(_app_context())
def _lookup_sse_job(job_id):
    return _runtime_facade.lookup_sse_job(_app_context(), job_id)

Handler = _create_handler_class(
    server_version=_WebDefaults.SERVER_VERSION,
    max_body_bytes=_WebDefaults.MAX_BODY_BYTES,
    dispatch_get=_dispatch_get,
    dispatch_post=_dispatch_post,
    dispatch_context=_handler_dispatch_context,
    web_session=_web_session,
    jobs=JOBS,
    resolve_sse_job=_lookup_sse_job,
    enrich_progress=_enrich_progress,
    content_security_policy_for_html=content_security_policy_for_html,
    sse_push_interval=_WebDefaults.SSE_PUSH_INTERVAL,
    max_sse_duration=_WebDefaults.MAX_SSE_DURATION,
    resolve_static_asset=_web_html.resolve_react_asset,
)

def run_job(job_id, payload):
    return _runtime_facade.run_job(_app_context(), job_id, payload)


def _compute_run_stats(data, run_config):
    return _compute_run_stats_service(data, run_config)


def generate_candidates_payload(payload):
    return _runtime_facade.generate_candidates_payload(_app_context(), payload)

def run_generate_candidates_job(job_id, payload):
    return _runtime_facade.run_generate_candidates_job(_app_context(), job_id, payload)

def run_scoring_evaluate_job(job_id, payload):
    return _runtime_facade.run_scoring_evaluate_job(_app_context(), job_id, payload)

def run_submit_batch_job(job_id, payload):
    return _runtime_facade.run_submit_batch_job(_app_context(), job_id, payload)


def lifecycle_from_job(job):
    return _runtime_facade.lifecycle_from_job(_app_context(), job)


# C4: Periodic lifecycle file archiving — prevent unbounded growth (>50MB → archive)
_LAST_ARCHIVE_CHECK: float = 0.0
_ARCHIVE_CHECK_INTERVAL: float = 3600.0  # check every hour


def _maybe_archive_lifecycle():
    return _runtime_facade.maybe_archive_lifecycle(_app_context())


# C2: Settings enum validation — fail fast on invalid values
_status_category = _status_category_service


def cloud_alpha_snapshot(limit=None):
    return _runtime_facade.cloud_alpha_snapshot(_app_context(), limit=limit)


def _snapshot_runtime():
    return _runtime_facade.snapshot_runtime(_app_context())


def _snapshot_facade():
    return _runtime_facade.snapshot_facade(_app_context())


def research_memory_snapshot(*, limit=5000, top_n=10):
    return _snapshot_facade().research_memory_snapshot(limit=limit, top_n=top_n)
def research_knowledge_snapshot(*, limit=100, min_confidence=0.0):
    return _snapshot_facade().research_knowledge_snapshot(limit=limit, min_confidence=min_confidence)
def research_observability_snapshot(*, limit=5000, top_n=10, include_cloud=True):
    return _snapshot_facade().research_observability_snapshot(limit=limit, top_n=top_n, include_cloud=include_cloud)
def prompt_run_ledger_snapshot(*, limit=100):
    return _snapshot_facade().prompt_run_ledger_snapshot(limit=limit)
def sqlite_index_snapshot(*, top_n=10):
    return _sqlite_index_snapshot_service(top_n=top_n, load_config=_load_run_config_provider(), web_error=_web_error)
def sqlite_expression_lookup_payload(*, expression, top_n=10, min_similarity=0.75, max_scan_rows=2000):
    return _sqlite_expression_lookup_payload_service(expression=expression, top_n=top_n, min_similarity=min_similarity, max_scan_rows=max_scan_rows, load_config=_load_run_config_provider(), web_error=_web_error)
def sqlite_record_lookup_payload(*, alpha_id, limit=50):
    return _sqlite_record_lookup_payload_service(alpha_id=alpha_id, limit=limit, load_config=_load_run_config_provider(), web_error=_web_error)
def _durable_job_rows(*, limit):
    return _snapshot_facade().durable_job_rows(limit=limit)
def assistant_guidance_snapshot(*, limit=100, min_confidence=None):
    return _snapshot_facade().assistant_guidance_snapshot(limit=limit, min_confidence=min_confidence)
def _assistant_guidance_history(rows, *, min_confidence, scoring_policy=None, outcomes_by_guidance=None):
    return _snapshot_facade().assistant_guidance_history(rows, min_confidence=min_confidence, scoring_policy=scoring_policy, outcomes_by_guidance=outcomes_by_guidance)
def assistant_context_snapshot(*, limit=5000, top_n=10, include_prompt=True, include_sensitive=False):
    return _snapshot_facade().assistant_context_snapshot(limit=limit, top_n=top_n, include_prompt=include_prompt, include_sensitive=include_sensitive)
def assistant_request_snapshot(*, limit=5000, top_n=10, include_prompt=True, include_offline_draft=True, include_sensitive=False):
    return _snapshot_facade().assistant_request_snapshot(limit=limit, top_n=top_n, include_prompt=include_prompt, include_offline_draft=include_offline_draft, include_sensitive=include_sensitive)
def assistant_response_parse_payload(payload):
    return _snapshot_facade().assistant_response_parse_payload(payload)
def assistant_response_guidance_payload(payload):
    return _snapshot_facade().assistant_response_guidance_payload(payload)
def anti_overfit_snapshot(candidate_id=''):
    return _snapshot_facade().anti_overfit_snapshot(candidate_id)
def rolling_validation_snapshot(candidate_id='', windows=4):
    return _snapshot_facade().rolling_validation_snapshot(candidate_id, windows)
def assistant_cross_review_payload(payload):
    return _snapshot_facade().assistant_cross_review_payload(payload)
def save_assistant_guidance_payload(payload):
    return _snapshot_facade().save_assistant_guidance_payload(payload)


def latest_result_snapshot():
    return _runtime_facade.latest_result_snapshot(_app_context())

def _latest_run_history_path():
    return _runtime_facade.latest_run_history_path(_app_context())

def _user_profile_snapshot():
    return _runtime_facade.user_profile_snapshot(_app_context())

# D1: Preset configuration — single source of truth for market presets
def _load_presets():
    return _runtime_facade.load_presets(_app_context())


def _match_preset_id(settings):
    return _runtime_facade.match_preset_id(_app_context(), settings)


_dedupe_cloud_alpha_rows = _dedupe_cloud_alpha_rows_service
def _latest_cached_user_alphas(limit=None):
    return _latest_cached_user_alphas_service(limit=limit, load_config=_load_run_config_provider())
def _latest_cached_user_alpha_path():
    return _latest_cached_user_alpha_path_service(load_config=_load_run_config_provider())
def _cached_user_alpha_paths():
    return _cached_user_alpha_paths_service(load_config=_load_run_config_provider())
_path_modified_at = _path_modified_at_service
_extract_alpha_rows = _extract_alpha_rows_service
def _official_context_file_counts():
    return _official_context_file_counts_service(load_config=_load_run_config_provider(), runtime_root=_runtime_project_root_provider(), safe_error_message=safe_error_message)
def _read_official_context_metadata(filename):
    return _read_official_context_metadata_service(filename, load_config=_load_run_config_provider(), runtime_root=_runtime_project_root_provider(), safe_error_message=safe_error_message)
def _read_official_context_json(filename):
    return _read_official_context_json_service(filename, load_config=_load_run_config_provider(), runtime_root=_runtime_project_root_provider(), safe_error_message=safe_error_message)
def _cloud_alpha_summary(rows):
    return _cloud_alpha_summary_service(rows, load_config=_load_run_config_provider(), runtime_root=_runtime_project_root_provider(), safe_error_message=safe_error_message)
_cloud_alpha_id = _cloud_alpha_id_service
_cloud_row_sort_key = _cloud_row_sort_key_service


def candidate_from_payload(payload):
    return _runtime_facade.candidate_from_payload(_app_context(), payload)


def sync_cloud_alphas(payload):
    return _runtime_facade.sync_cloud_alphas(_app_context(), payload)


def run_sync_job(job_id, payload):
    return _runtime_facade.run_sync_job(_app_context(), job_id, payload)


def run_check_batch_job(job_id, payload):
    return _runtime_facade.run_check_batch_job(_app_context(), job_id, payload)


def refresh_cloud_context_for_check(api, repo, sync_range, job_id, total, mode, region='', refresh_remote=False):
    return _runtime_facade.refresh_cloud_context_for_check(_app_context(), api, repo, sync_range, job_id, total, mode, region, refresh_remote=refresh_remote)


def _datasets_from_fields(fields):
    return _runtime_facade.datasets_from_fields(_app_context(), fields)


def _persist_official_context(fields, operators, datasets):
    return _runtime_facade.persist_official_context(_app_context(), fields, operators, datasets)


def _save_official_context_json(filename, items):
    return _runtime_facade.save_official_context_json(_app_context(), filename, items)


def passed_candidates_from_payload(payload):
    return _runtime_facade.passed_candidates_from_payload(_app_context(), payload)


def check_candidate_availability(candidate, mode, api, ledger, cloud_alphas, cloud_error='', observability_preflight=None):
    return _runtime_facade.check_candidate_availability(_app_context(), candidate, mode, api, ledger, cloud_alphas, cloud_error, observability_preflight)


def cloud_status_for(candidate, cloud_alphas):
    return _runtime_facade.cloud_status_for(_app_context(), candidate, cloud_alphas)


def cloud_similarity_risk(candidate, cloud_alphas):
    return _runtime_facade.cloud_similarity_risk(_app_context(), candidate, cloud_alphas)


def check_candidate(payload):
    return _runtime_facade.check_candidate(_app_context(), payload)


def submission_preflight_error(candidate, run_config):
    return _runtime_facade.submission_preflight_error(_app_context(), candidate, run_config)


_submit_preflight_block = _submission_preflight_block_service


def submission_preflight_advisory(candidate, run_config):
    return _runtime_facade.submission_preflight_advisory(_app_context(), candidate, run_config)


def observability_submission_preflight(storage_dir, limit=5000, top_n=5):
    return _runtime_facade.observability_submission_preflight(_app_context(), storage_dir, limit=limit, top_n=top_n)


cloud_row_expression = _cloud_row_expression


def record_submit_blocked(payload, candidate, run_config, failure_reason):
    return _runtime_facade.record_submit_blocked(_app_context(), payload, candidate, run_config, failure_reason)


def submit_candidate(payload):
    return _runtime_facade.submit_candidate(_app_context(), payload)


def load_check_results():
    return _runtime_facade.load_check_results(_app_context())


def submit_batch(payload):
    return _runtime_facade.submit_batch(_app_context(), payload)


def _storage_jsonl_path(filename):
    return _runtime_facade.storage_jsonl_path(_app_context(), filename)


def _read_storage_jsonl(filename, limit=500):
    return _runtime_facade.read_storage_jsonl(_app_context(), filename, limit=limit)


def _read_storage_jsonl_stats(filename, limit=500):
    return _runtime_facade.read_storage_jsonl_stats(_app_context(), filename, limit=limit)


_tail_text_lines = _tail_text_lines_service


def public_run_config():
    return _runtime_facade.public_run_config(_app_context())


def find_free_port(start=DEFAULT_PORT, host=HOST):
    return _runtime_facade.find_free_port(_app_context(), start, host)


def shutdown_server():
    return _runtime_facade.shutdown_server(_app_context())


def serve(port=None, open_browser=True, host=HOST, session_ttl_seconds=None, allow_multiple_sessions=None, allow_remote=False, secure_cookies=None):
    return _runtime_facade.serve(_app_context(), port=port, open_browser=open_browser, host=host, session_ttl_seconds=session_ttl_seconds, allow_multiple_sessions=allow_multiple_sessions, allow_remote=allow_remote, secure_cookies=secure_cookies)


def smoke_test_server(port=None):
    return _runtime_facade.smoke_test_server(_app_context(), port=port)


def main(argv=None):
    return _runtime_facade.main(_app_context(), argv)


if __name__ == "__main__":
    raise SystemExit(main())
