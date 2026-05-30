"""Tiny local web console for BRAIN Alpha Ops.

The server uses only Python's standard library. It is intentionally local-only
and keeps credentials in memory for the current request.
"""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import logging
from pathlib import Path
import sys
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
    save_run_config_payload as _save_run_config_payload,
)
from brain_alpha_ops.web_config_schema import public_config_schema
from brain_alpha_ops import web_html
from brain_alpha_ops import web_runtime_facade as _runtime_facade
from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS, DEFAULT_OPERATORS
from brain_alpha_ops.jsonl import tail_text_lines
from brain_alpha_ops.observability import error_payload
from brain_alpha_ops.task_executor import ThreadTaskExecutor
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger
from brain_alpha_ops.runner import api_from_run_config, run_pipeline_from_config
from brain_alpha_ops.tasks import JobStore as DurableJobStore
from brain_alpha_ops.web_check_availability import (
    check_candidate_availability as _check_candidate_availability,
    cloud_row_expression as _cloud_row_expression,
    cloud_similarity_risk as _cloud_similarity_risk,
    cloud_status_for as _cloud_status_for,
)
from brain_alpha_ops.web_check_batch_job import run_check_batch_job_service
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
from brain_alpha_ops.web_rate_limit import RequestRateLimiter
from brain_alpha_ops.web_handler_dispatch import WebHandlerDispatchContext, dispatch_get, dispatch_post
from brain_alpha_ops.web_http_handler import create_handler_class
from brain_alpha_ops.web_routes import route_for
from brain_alpha_ops.web_async_jobs import progress_update, run_simple_async_job_service
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
from brain_alpha_ops import web_session
from brain_alpha_ops.web_snapshot_facade import WebSnapshotFacade
from brain_alpha_ops.web_snapshot_runtime import WebSnapshotRuntime
from brain_alpha_ops.web_security import (
    DEFAULT_SESSION_TTL_SECONDS,
    LOOPBACK_BIND_HOSTS,
    SESSION_COOKIE_NAME,
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
from brain_alpha_ops.web_submission_batch import submit_batch_payload
from brain_alpha_ops.web_submission_single import submit_candidate_payload
from brain_alpha_ops.web_submission_safety import (
    observability_submission_preflight as _observability_submission_preflight,
    record_submit_blocked_event as _record_submit_blocked_event,
    submission_preflight_advisory as _submission_preflight_advisory,
    submission_preflight_error_message as _submission_preflight_error_message,
    submit_preflight_block as _submission_preflight_block_service,
)
from brain_alpha_ops.web_sync_job import run_sync_job_service
from brain_alpha_ops.web_sync_payload import sync_cloud_alphas_payload


# ── Runtime constants (centralized in runtime_constants.py) ──
from brain_alpha_ops.runtime_constants import CloudDefaults, WebDefaults, SnapshotDefaults

HOST = WebDefaults.HOST
DEFAULT_PORT = WebDefaults.PORT
CLOUD_SYNC_STALE_SECONDS = CloudDefaults.CLOUD_SYNC_STALE_SECONDS
SESSION_TTL_SECONDS = DEFAULT_SESSION_TTL_SECONDS
SESSION_ALLOW_MULTIPLE = True
SESSION_MANAGER = web_session.SESSION_MANAGER
SESSIONS = web_session.SESSIONS
SESSION_LOCK = web_session.SESSION_LOCK

# Allowed base URLs per environment — used to prevent SSRF via frontend.
HTML = _HTML_CACHE = ""


_header_hostname = _header_hostname_service
_header_port = _header_port_service
_path_requires_session = _path_requires_session_service


def configure_session_policy(
    ttl_seconds: int | float | None = None,
    allow_multiple_sessions: bool | None = None,
    secure_cookies: bool | None = None,
) -> None:
    global SESSION_TTL_SECONDS, SESSION_ALLOW_MULTIPLE
    web_session.configure_session_policy(ttl_seconds, allow_multiple_sessions, secure_cookies)
    SESSION_TTL_SECONDS = web_session.session_ttl_seconds()
    SESSION_ALLOW_MULTIPLE = web_session.session_allow_multiple()


_parse_cookies = _parse_cookies_service
_session_cookie_header = web_session.session_cookie_header
_expired_session_cookie_header = web_session.expired_session_cookie_header
_prune_sessions = web_session.prune_sessions
_create_session = web_session.create_session
_expire_session = web_session.expire_session
_validate_session_token = web_session.validate_session_token
_validate_session = web_session.validate_session
_validate_stream_session = web_session.validate_stream_session
_csrf_for_session = web_session.csrf_for_session
_stream_token_for_session = web_session.stream_token_for_session
_get_or_create_session = web_session.get_or_create_session
_remote_admin_required = web_session.remote_admin_required
_has_valid_admin_token = web_session.has_valid_admin_token

safe_error_message = _safe_error_message_service
safe_error_payload = _safe_error_payload_service
_web_error = _web_error_payload_service
_load_html = web_html.load_html
_render_html = web_html.render_html
_script_hash_sources = web_html.script_hash_sources
_style_hash_sources = web_html.style_hash_sources
content_security_policy_for_html = web_html.content_security_policy_for_html

run_config_from_payload = lambda payload: _run_config_from_payload(payload, loader=load_run_config)
config_from_payload = lambda payload: _config_from_payload(payload, loader=load_run_config)
save_run_config_payload = lambda payload: _save_run_config_payload(payload, loader=load_run_config)


test_connection = lambda payload: _runtime_facade.test_connection(sys.modules[__name__], payload)


_enrich_progress = _enrich_progress_service


JOBS = DurableJobStore(runtime_project_root() / "data" / "jobs_production.json")
SYNC_JOBS = DurableJobStore(runtime_project_root() / "data" / "jobs_sync.json", job_prefix="sync")
CHECK_JOBS = DurableJobStore(runtime_project_root() / "data" / "jobs_check.json", job_prefix="check")
ASYNC_JOBS = DurableJobStore(runtime_project_root() / "data" / "jobs_async.json", job_prefix="task")
SUBMIT_LOCK = threading.Lock()
RATE_LIMITER = RequestRateLimiter()
TASK_EXECUTOR = ThreadTaskExecutor(max_workers=4)
SERVER: ThreadingHTTPServer | None = None
SERVER_STOP = threading.Event()


active_auxiliary_operation = lambda exclude="", allow_production=False: _active_auxiliary_operation_service(production_store=JOBS, sync_store=SYNC_JOBS, check_store=CHECK_JOBS, submit_lock=SUBMIT_LOCK, exclude=exclude, allow_production=allow_production)
rate_limit_request = lambda key, method, path: RATE_LIMITER.check(key=key, method=method, path=path)


def normalize_host(host: str | None) -> str:
    return web_session.normalize_host(host, default_host=HOST)


def _start_thread(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def _submit_background_job(target, *args) -> None:
    TASK_EXECUTOR.submit(target, *args)


_handler_dispatch_context = lambda: _runtime_facade.handler_dispatch_context(sys.modules[__name__])
_lookup_sse_job = lambda job_id: _runtime_facade.lookup_sse_job(sys.modules[__name__], job_id)

Handler = create_handler_class(
    server_version=WebDefaults.SERVER_VERSION,
    max_body_bytes=WebDefaults.MAX_BODY_BYTES,
    dispatch_get=dispatch_get,
    dispatch_post=dispatch_post,
    dispatch_context=_handler_dispatch_context,
    web_session=web_session,
    jobs=JOBS,
    resolve_sse_job=_lookup_sse_job,
    enrich_progress=_enrich_progress,
    content_security_policy_for_html=content_security_policy_for_html,
    sse_push_interval=WebDefaults.SSE_PUSH_INTERVAL,
    max_sse_duration=WebDefaults.MAX_SSE_DURATION,
    resolve_static_asset=web_html.resolve_react_asset,
)

run_job = lambda job_id, payload: _runtime_facade.run_job(sys.modules[__name__], job_id, payload)


_compute_run_stats = lambda data, run_config: _compute_run_stats_service(data, run_config)


generate_candidates_payload = lambda payload: _runtime_facade.generate_candidates_payload(sys.modules[__name__], payload)

run_generate_candidates_job = lambda job_id, payload: _runtime_facade.run_generate_candidates_job(sys.modules[__name__], job_id, payload)

run_scoring_evaluate_job = lambda job_id, payload: _runtime_facade.run_scoring_evaluate_job(sys.modules[__name__], job_id, payload)

run_submit_batch_job = lambda job_id, payload: _runtime_facade.run_submit_batch_job(sys.modules[__name__], job_id, payload)


lifecycle_from_job = lambda job: _runtime_facade.lifecycle_from_job(sys.modules[__name__], job)


# C4: Periodic lifecycle file archiving — prevent unbounded growth (>50MB → archive)
_LAST_ARCHIVE_CHECK: float = 0.0
_ARCHIVE_CHECK_INTERVAL: float = 3600.0  # check every hour


_maybe_archive_lifecycle = lambda: _runtime_facade.maybe_archive_lifecycle(sys.modules[__name__])


# C2: Settings enum validation — fail fast on invalid values
_status_category = _status_category_service


cloud_alpha_snapshot = lambda limit=None: _runtime_facade.cloud_alpha_snapshot(sys.modules[__name__], limit=limit)


_snapshot_runtime = lambda: _runtime_facade.snapshot_runtime(sys.modules[__name__])


_snapshot_facade = lambda: _runtime_facade.snapshot_facade(sys.modules[__name__])


research_memory_snapshot = lambda *, limit=5000, top_n=10: _snapshot_facade().research_memory_snapshot(limit=limit, top_n=top_n)
research_knowledge_snapshot = lambda *, limit=100, min_confidence=0.0: _snapshot_facade().research_knowledge_snapshot(
    limit=limit, min_confidence=min_confidence
)
research_observability_snapshot = lambda *, limit=5000, top_n=10, include_cloud=True: _snapshot_facade().research_observability_snapshot(
    limit=limit, top_n=top_n, include_cloud=include_cloud
)
prompt_run_ledger_snapshot = lambda *, limit=100: _snapshot_facade().prompt_run_ledger_snapshot(limit=limit)
sqlite_index_snapshot = lambda *, top_n=10: _sqlite_index_snapshot_service(
    top_n=top_n, load_config=load_run_config, web_error=_web_error
)
sqlite_expression_lookup_payload = lambda *, expression, top_n=10, min_similarity=0.75, max_scan_rows=2000: _sqlite_expression_lookup_payload_service(
    expression=expression,
    top_n=top_n,
    min_similarity=min_similarity,
    max_scan_rows=max_scan_rows,
    load_config=load_run_config,
    web_error=_web_error,
)
sqlite_record_lookup_payload = lambda *, alpha_id, limit=50: _sqlite_record_lookup_payload_service(
    alpha_id=alpha_id, limit=limit, load_config=load_run_config, web_error=_web_error
)
_durable_job_rows = lambda *, limit: _snapshot_facade().durable_job_rows(limit=limit)
assistant_guidance_snapshot = lambda *, limit=100, min_confidence=None: _snapshot_facade().assistant_guidance_snapshot(
    limit=limit, min_confidence=min_confidence
)
_assistant_guidance_history = lambda rows, *, min_confidence, scoring_policy=None, outcomes_by_guidance=None: _snapshot_facade().assistant_guidance_history(
    rows,
    min_confidence=min_confidence,
    scoring_policy=scoring_policy,
    outcomes_by_guidance=outcomes_by_guidance,
)
assistant_context_snapshot = lambda *, limit=5000, top_n=10, include_prompt=True, include_sensitive=False: _snapshot_facade().assistant_context_snapshot(
    limit=limit, top_n=top_n, include_prompt=include_prompt, include_sensitive=include_sensitive
)
assistant_request_snapshot = lambda *, limit=5000, top_n=10, include_prompt=True, include_offline_draft=True, include_sensitive=False: _snapshot_facade().assistant_request_snapshot(
    limit=limit,
    top_n=top_n,
    include_prompt=include_prompt,
    include_offline_draft=include_offline_draft,
    include_sensitive=include_sensitive,
)
assistant_response_parse_payload = lambda payload: _snapshot_facade().assistant_response_parse_payload(payload)
assistant_response_guidance_payload = lambda payload: _snapshot_facade().assistant_response_guidance_payload(payload)
anti_overfit_snapshot = lambda candidate_id="": _snapshot_facade().anti_overfit_snapshot(candidate_id)
rolling_validation_snapshot = lambda candidate_id="", windows=4: _snapshot_facade().rolling_validation_snapshot(candidate_id, windows)
assistant_cross_review_payload = lambda payload: _snapshot_facade().assistant_cross_review_payload(payload)
save_assistant_guidance_payload = lambda payload: _snapshot_facade().save_assistant_guidance_payload(payload)


latest_result_snapshot = lambda: _runtime_facade.latest_result_snapshot(sys.modules[__name__])

_latest_run_history_path = lambda: _runtime_facade.latest_run_history_path(sys.modules[__name__])

_user_profile_snapshot = lambda: _runtime_facade.user_profile_snapshot(sys.modules[__name__])

# D1: Preset configuration — single source of truth for market presets
_load_presets = lambda: _runtime_facade.load_presets(sys.modules[__name__])


_match_preset_id = lambda settings: _runtime_facade.match_preset_id(sys.modules[__name__], settings)


_dedupe_cloud_alpha_rows = _dedupe_cloud_alpha_rows_service
_latest_cached_user_alphas = lambda limit=None: _latest_cached_user_alphas_service(limit=limit, load_config=load_run_config)
_latest_cached_user_alpha_path = lambda: _latest_cached_user_alpha_path_service(load_config=load_run_config)
_cached_user_alpha_paths = lambda: _cached_user_alpha_paths_service(load_config=load_run_config)
_path_modified_at = _path_modified_at_service
_extract_alpha_rows = _extract_alpha_rows_service
_official_context_file_counts = lambda: _official_context_file_counts_service(
    load_config=load_run_config, runtime_root=runtime_project_root, safe_error_message=safe_error_message
)
_read_official_context_metadata = lambda filename: _read_official_context_metadata_service(
    filename,
    load_config=load_run_config,
    runtime_root=runtime_project_root,
    safe_error_message=safe_error_message,
)
_read_official_context_json = lambda filename: _read_official_context_json_service(
    filename, load_config=load_run_config, runtime_root=runtime_project_root, safe_error_message=safe_error_message
)
_cloud_alpha_summary = lambda rows: _cloud_alpha_summary_service(
    rows, load_config=load_run_config, runtime_root=runtime_project_root, safe_error_message=safe_error_message
)
_cloud_alpha_id = _cloud_alpha_id_service
_cloud_row_sort_key = _cloud_row_sort_key_service


candidate_from_payload = lambda payload: _runtime_facade.candidate_from_payload(sys.modules[__name__], payload)


sync_cloud_alphas = lambda payload: _runtime_facade.sync_cloud_alphas(sys.modules[__name__], payload)


run_sync_job = lambda job_id, payload: _runtime_facade.run_sync_job(sys.modules[__name__], job_id, payload)


run_check_batch_job = lambda job_id, payload: _runtime_facade.run_check_batch_job(sys.modules[__name__], job_id, payload)


refresh_cloud_context_for_check = lambda api, repo, sync_range, job_id, total, mode, region="", refresh_remote=False: _runtime_facade.refresh_cloud_context_for_check(sys.modules[__name__], api, repo, sync_range, job_id, total, mode, region, refresh_remote=refresh_remote)


_datasets_from_fields = lambda fields: _runtime_facade.datasets_from_fields(sys.modules[__name__], fields)


_persist_official_context = lambda fields, operators, datasets: _runtime_facade.persist_official_context(sys.modules[__name__], fields, operators, datasets)


_save_official_context_json = lambda filename, items: _runtime_facade.save_official_context_json(sys.modules[__name__], filename, items)


passed_candidates_from_payload = lambda payload: _runtime_facade.passed_candidates_from_payload(sys.modules[__name__], payload)


check_candidate_availability = lambda candidate, mode, api, ledger, cloud_alphas, cloud_error="", observability_preflight=None: _runtime_facade.check_candidate_availability(sys.modules[__name__], candidate, mode, api, ledger, cloud_alphas, cloud_error, observability_preflight)


cloud_status_for = lambda candidate, cloud_alphas: _runtime_facade.cloud_status_for(sys.modules[__name__], candidate, cloud_alphas)


cloud_similarity_risk = lambda candidate, cloud_alphas: _runtime_facade.cloud_similarity_risk(sys.modules[__name__], candidate, cloud_alphas)


check_candidate = lambda payload: _runtime_facade.check_candidate(sys.modules[__name__], payload)


submission_preflight_error = lambda candidate, run_config: _runtime_facade.submission_preflight_error(sys.modules[__name__], candidate, run_config)


_submit_preflight_block = _submission_preflight_block_service


submission_preflight_advisory = lambda candidate, run_config: _runtime_facade.submission_preflight_advisory(sys.modules[__name__], candidate, run_config)


observability_submission_preflight = lambda storage_dir, limit=5000, top_n=5: _runtime_facade.observability_submission_preflight(sys.modules[__name__], storage_dir, limit=limit, top_n=top_n)


cloud_row_expression = _cloud_row_expression


record_submit_blocked = lambda payload, candidate, run_config, failure_reason: _runtime_facade.record_submit_blocked(sys.modules[__name__], payload, candidate, run_config, failure_reason)


submit_candidate = lambda payload: _runtime_facade.submit_candidate(sys.modules[__name__], payload)


load_check_results = lambda: _runtime_facade.load_check_results(sys.modules[__name__])


submit_batch = lambda payload: _runtime_facade.submit_batch(sys.modules[__name__], payload)


_storage_jsonl_path = lambda filename: _runtime_facade.storage_jsonl_path(sys.modules[__name__], filename)


_read_storage_jsonl = lambda filename, limit=500: _runtime_facade.read_storage_jsonl(sys.modules[__name__], filename, limit=limit)


_read_storage_jsonl_stats = lambda filename, limit=500: _runtime_facade.read_storage_jsonl_stats(sys.modules[__name__], filename, limit=limit)


_tail_text_lines = tail_text_lines


public_run_config = lambda: _runtime_facade.public_run_config(sys.modules[__name__])


find_free_port = lambda start=DEFAULT_PORT, host=HOST: _runtime_facade.find_free_port(sys.modules[__name__], start, host)


shutdown_server = lambda: _runtime_facade.shutdown_server(sys.modules[__name__])


serve = lambda port=None, open_browser=True, host=HOST, session_ttl_seconds=None, allow_multiple_sessions=None, allow_remote=False, secure_cookies=None: _runtime_facade.serve(sys.modules[__name__], port=port, open_browser=open_browser, host=host, session_ttl_seconds=session_ttl_seconds, allow_multiple_sessions=allow_multiple_sessions, allow_remote=allow_remote, secure_cookies=secure_cookies)


smoke_test_server = lambda port=None: _runtime_facade.smoke_test_server(sys.modules[__name__], port=port)


main = lambda argv=None: _runtime_facade.main(sys.modules[__name__], argv)


if __name__ == "__main__":
    raise SystemExit(main())
