"""Web service namespace builder (Phase 1-B: imports from stub wrappers)."""

from __future__ import annotations

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
import brain_alpha_ops.web_html as _web_html
from brain_alpha_ops.web_html import load_html as _load_html_service, resolve_react_asset as _resolve_react_asset_service, content_security_policy_for_html as _content_security_policy_for_html_service
from brain_alpha_ops.web_runtime_facade import compute_run_stats as _compute_run_stats_service, status_category as _status_category_service
from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS as _DEFAULT_FIELDS, DEFAULT_OPERATORS as _DEFAULT_OPERATORS
from brain_alpha_ops.jsonl import tail_text_lines as _tail_text_lines_service
from brain_alpha_ops.observability import error_payload as _error_payload
from brain_alpha_ops.task_executor import ThreadTaskExecutor as _ThreadTaskExecutor
from brain_alpha_ops.web_job_registry import WebJobRegistry as _WebJobRegistry
from brain_alpha_ops.research.observability import build_research_observability_snapshot as _build_research_observability_snapshot
from brain_alpha_ops.research.repository import ResearchRepository as _ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger as _SubmissionLedger
from brain_alpha_ops.runner import api_from_run_config as _api_from_run_config, run_pipeline_from_config as _run_pipeline_from_config
from brain_alpha_ops.submission_readiness import live_submit_readiness_hard_gate as _live_submit_readiness_hard_gate
from brain_alpha_ops.tasks import JobStore as _DurableJobStore
from brain_alpha_ops.web_check_availability import (
    check_candidate_availability as _check_candidate_availability,
    cloud_row_expression as _cloud_row_expression,
    cloud_similarity_risk as _cloud_similarity_risk,
    cloud_status_for as _cloud_status_for,
)
from brain_alpha_ops.web_check_batch_job import run_check_batch_job_service as _run_check_batch_job_service
from brain_alpha_ops.web_cloud_snapshot import (
    cloud_alpha_snapshot as _cloud_alpha_snapshot_service,
    persist_official_context as _persist_official_context_service,
    storage_jsonl_path as _storage_jsonl_path_service,
    read_storage_jsonl as _read_storage_jsonl_service,
    read_storage_jsonl_stats as _read_storage_jsonl_stats_service,
    read_official_context_json as _read_official_context_json_service,
    read_official_context_metadata as _read_official_context_metadata_service,
)
from brain_alpha_ops.web_candidate_generation import generate_candidates_payload as _generate_candidates_payload
from brain_alpha_ops.web_candidate_selection import (
    is_passed_candidate_for_check as _is_passed_candidate_for_check,
    official_alpha_id as _official_alpha_id,
)
from brain_alpha_ops.web_candidate_check import check_candidate_payload as _check_candidate_payload
from brain_alpha_ops.web_cloud_snapshot import cloud_alpha_summary as _cloud_alpha_summary_service
from brain_alpha_ops.web_cloud_context_refresh import refresh_cloud_context_for_check_service as _refresh_cloud_context_for_check_service
from brain_alpha_ops.web.handlers.sync import (
    active_job_payload as _active_job_payload,
    health_payload as _health_payload,
    job_status_payload as _job_status_payload,
    lifecycle_payload as _lifecycle_payload,
    presets_payload as _presets_payload,
    profile_payload as _profile_payload,
)
from brain_alpha_ops.web_assistant_snapshots import (
    assistant_response_guidance_post_payload as _assistant_response_guidance_post_payload,
    assistant_response_parse_post_payload as _assistant_response_parse_post_payload,
)
from brain_alpha_ops.web_async_jobs import (
    background_job_start_payload as _background_job_start_payload,
)
from brain_alpha_ops.web_sync_payload import (
    connection_test_post_payload as _connection_test_post_payload,
)
from brain_alpha_ops.web_submission_safety import (
    save_assistant_guidance_post_payload as _save_assistant_guidance_post_payload,
)
from brain_alpha_ops.web_session import session_end_payload as _session_end_payload
from brain_alpha_ops.web_handler_dispatch import stop_job_payload as _stop_job_payload
from brain_alpha_ops.web_rate_limit import RequestRateLimiter as _RequestRateLimiter
from brain_alpha_ops.web_dispatch_context import (
    WebDispatchActionContext as _WebDispatchActionContext,
    WebDispatchAssistantContext as _WebDispatchAssistantContext,
    WebDispatchConfigContext as _WebDispatchConfigContext,
    WebDispatchCoreContext as _WebDispatchCoreContext,
    WebDispatchJobContext as _WebDispatchJobContext,
    WebDispatchResearchContext as _WebDispatchResearchContext,
    WebDispatchSessionContext as _WebDispatchSessionContext,
    WebHandlerDispatchContext as _WebHandlerDispatchContext,
)
from brain_alpha_ops.web_handler_dispatch import dispatch_get as _dispatch_get, dispatch_post as _dispatch_post
from brain_alpha_ops.web_http_handler import create_handler_class as _create_handler_class
from brain_alpha_ops.web_routes import route_for as _route_for
from brain_alpha_ops.web_async_jobs import progress_update as _progress_update, run_simple_async_job_service as _run_simple_async_job_service
from brain_alpha_ops.web_run_job import run_guided_job_service as _run_guided_job_service, run_job_service as _run_job_service
from brain_alpha_ops.web_session import (
    clear_brain_connection_verified as _clear_brain_connection_verified_service,
    create_session as _create_session_service,
    csrf_for_session as _csrf_for_session_service,
    expired_session_cookie_header as _expired_session_cookie_header_service,
    expire_session as _expire_session_service,
    header_hostname as _header_hostname_service,
    header_port as _header_port_service,
    mark_brain_connection_verified as _mark_brain_connection_verified_service,
    payload_with_brain_session_credentials as _payload_with_brain_session_credentials_service,
    session_status as _session_status_service,
)
import brain_alpha_ops.web_session as _web_session
from brain_alpha_ops.web_session import (
    get_or_create_session as _get_or_create_session_service,
    has_valid_admin_token as _has_valid_admin_token_service,
    normalize_host as _normalize_host_service,
    parse_cookies as _parse_cookies_service,
    path_requires_session as _path_requires_session_service,
    prune_sessions as _prune_sessions_service,
    remote_admin_required as _remote_admin_required_service,
)
from brain_alpha_ops.web_session import (
    session_cookie_header as _session_cookie_header_service,
    stream_token_for_session as _stream_token_for_session_service,
    validate_session as _validate_session_service,
    validate_session_token as _validate_session_token_service,
    validate_stream_session as _validate_stream_session_service,
)
from brain_alpha_ops.web_html import (
    content_security_policy_for_html as _content_security_policy_for_html,
    load_html as _load_html,
    render_html as _render_html_service,
    script_hash_sources as _script_hash_sources_service,
    style_hash_sources as _style_hash_sources_service,
)
from brain_alpha_ops.web_html import resolve_react_asset as _resolve_react_asset
from brain_alpha_ops.web_errors import (
    safe_error_message as _safe_error_message_service,
    safe_error_payload as _safe_error_payload_service,
    web_error_payload as _web_error_payload_service,
)
from brain_alpha_ops.web_progress import enrich_progress as _enrich_progress_service
from brain_alpha_ops.web_server_lifecycle import (
    find_free_port as _find_free_port_service,
    serve as _serve,
    shutdown_server as _shutdown_server_service,
    smoke_test_server as _smoke_test_server_service,
)
from brain_alpha_ops.web_runtime_state import (
    active_auxiliary_operation as _active_auxiliary_operation_service,
    lifecycle_from_job as _lifecycle_from_job_service,
    load_check_results as _load_check_results_service,
    load_presets as _load_presets_service,
    match_preset_id as _match_preset_id_service,
    maybe_archive_lifecycle as _maybe_archive_lifecycle_service,
)
from brain_alpha_ops.web_snapshot_facade import WebSnapshotFacade as _WebSnapshotFacade
from brain_alpha_ops.web_snapshot_runtime import WebSnapshotRuntime as _WebSnapshotRuntime
from brain_alpha_ops.web_security import (
    DEFAULT_SESSION_TTL_SECONDS as _DEFAULT_SESSION_TTL_SECONDS,
    LOOPBACK_BIND_HOSTS as _LOOPBACK_BIND_HOSTS,
    SESSION_COOKIE_NAME as _SESSION_COOKIE_NAME,
)
from brain_alpha_ops.web_submission_batch import submit_batch_payload as _submit_batch_payload
from brain_alpha_ops.web_submission_single import submit_candidate_payload as _submit_candidate_payload
from brain_alpha_ops.web_submission_safety import (
    submission_preflight_block as _submission_preflight_block_service,
    submission_preflight_error as _submission_preflight_error_service,
)
from brain_alpha_ops.web_submission_safety import (
    candidate_official_metrics as _candidate_official_metrics_service,
    dedupe_cloud_alpha_rows as _dedupe_cloud_alpha_rows_service,
    extract_alpha_rows as _extract_alpha_rows_service,
)
from brain_alpha_ops.web.handlers.sync import (
    cloud_alpha_id as _cloud_alpha_id_service,
    cloud_row_sort_key as _cloud_row_sort_key_service,
    run_sync_job_service as _run_sync_job_service,
    sync_cloud_alphas_payload as _sync_cloud_alphas_payload,
)
from brain_alpha_ops.web_sync_job import path_modified_at as _path_modified_at_service
from brain_alpha_ops.web_sync_payload import (
    official_context_file_counts as _official_context_file_counts_service,
    latest_cached_user_alphas as _latest_cached_user_alphas_service,
    latest_cached_user_alpha_path as _latest_cached_user_alpha_path_service,
    cached_user_alpha_paths as _cached_user_alpha_paths_service,
    save_official_context_json as _save_official_context_json_service,
)
from brain_alpha_ops.web_sqlite_indexes import (
    sqlite_expression_lookup_payload as _sqlite_expression_lookup_payload_service,
    sqlite_index_snapshot as _sqlite_index_snapshot_service,
    sqlite_record_lookup_payload as _sqlite_record_lookup_payload_service,
)
from brain_alpha_ops.runtime_constants import CloudDefaults as _CloudDefaults, SnapshotDefaults as _SnapshotDefaults, WebDefaults as _WebDefaults


def build_web_service_namespace():
    return {
        "_RunConfig": _RunConfig,
        "_load_run_config": _load_run_config,
        "_runtime_project_root": _runtime_project_root,
        "_MAX_CANDIDATES": _MAX_CANDIDATES,
        "_MAX_VALIDATIONS": _MAX_VALIDATIONS,
        "_MAX_SIMULATIONS": _MAX_SIMULATIONS,
        "_MAX_CONCURRENT_SIMULATIONS": _MAX_CONCURRENT_SIMULATIONS,
        "_MAX_POOL_SIZE": _MAX_POOL_SIZE,
        "_MAX_CYCLES": _MAX_CYCLES,
        "_MAX_CYCLE_PAUSE_SECONDS": _MAX_CYCLE_PAUSE_SECONDS,
        "_MAX_BACKTEST_BATCH_SIZE": _MAX_BACKTEST_BATCH_SIZE,
        "_bounded_query_float": _bounded_query_float,
        "_bounded_query_int": _bounded_query_int,
        "_config_from_payload": _config_from_payload,
        "_payload_truthy": _payload_truthy,
        "_run_config_from_payload": _run_config_from_payload,
        "_save_run_config_payload": _save_run_config_payload,
        "_public_config_schema": _public_config_schema,
        "_load_html_service": _load_html_service,
        "_web_html": _web_html,
        "_resolve_react_asset_service": _resolve_react_asset_service,
        "_content_security_policy_for_html_service": _content_security_policy_for_html_service,
        "_serve_service": _serve,
        "_compute_run_stats_service": _compute_run_stats_service,
        "_status_category_service": _status_category_service,
        "_DEFAULT_FIELDS": _DEFAULT_FIELDS,
        "_DEFAULT_OPERATORS": _DEFAULT_OPERATORS,
        "_tail_text_lines_service": _tail_text_lines_service,
        "_error_payload": _error_payload,
        "_ThreadTaskExecutor": _ThreadTaskExecutor,
        "_WebJobRegistry": _WebJobRegistry,
        "_build_research_observability_snapshot": _build_research_observability_snapshot,
        "_ResearchRepository": _ResearchRepository,
        "_SubmissionLedger": _SubmissionLedger,
        "_api_from_run_config": _api_from_run_config,
        "_run_pipeline_from_config": _run_pipeline_from_config,
        "_DurableJobStore": _DurableJobStore,
        "_check_candidate_availability": _check_candidate_availability,
        "_cloud_row_expression": _cloud_row_expression,
        "_cloud_similarity_risk": _cloud_similarity_risk,
        "_cloud_status_for": _cloud_status_for,
        "_run_check_batch_job_service": _run_check_batch_job_service,
        "_cloud_alpha_snapshot_service": _cloud_alpha_snapshot_service,
        "_persist_official_context_service": _persist_official_context_service,
        "_storage_jsonl_path_service": _storage_jsonl_path_service,
        "_read_storage_jsonl_service": _read_storage_jsonl_service,
        "_read_storage_jsonl_stats_service": _read_storage_jsonl_stats_service,
        "_read_official_context_json_service": _read_official_context_json_service,
        "_read_official_context_metadata_service": _read_official_context_metadata_service,
        "_generate_candidates_payload": _generate_candidates_payload,
        "_is_passed_candidate_for_check": _is_passed_candidate_for_check,
        "_official_alpha_id": _official_alpha_id,
        "_check_candidate_payload": _check_candidate_payload,
        "_cloud_alpha_summary_service": _cloud_alpha_summary_service,
        "_refresh_cloud_context_for_check_service": _refresh_cloud_context_for_check_service,
        "_active_job_payload": _active_job_payload,
        "_health_payload": _health_payload,
        "_job_status_payload": _job_status_payload,
        "_lifecycle_payload": _lifecycle_payload,
        "_presets_payload": _presets_payload,
        "_profile_payload": _profile_payload,
        "_assistant_response_guidance_post_payload": _assistant_response_guidance_post_payload,
        "_assistant_response_parse_post_payload": _assistant_response_parse_post_payload,
        "_background_job_start_payload": _background_job_start_payload,
        "_connection_test_post_payload": _connection_test_post_payload,
        "_save_assistant_guidance_post_payload": _save_assistant_guidance_post_payload,
        "_session_end_payload": _session_end_payload,
        "_stop_job_payload": _stop_job_payload,
        "_RequestRateLimiter": _RequestRateLimiter,
        "_WebDispatchActionContext": _WebDispatchActionContext,
        "_WebDispatchAssistantContext": _WebDispatchAssistantContext,
        "_WebDispatchConfigContext": _WebDispatchConfigContext,
        "_WebDispatchCoreContext": _WebDispatchCoreContext,
        "_WebDispatchJobContext": _WebDispatchJobContext,
        "_WebDispatchResearchContext": _WebDispatchResearchContext,
        "_WebDispatchSessionContext": _WebDispatchSessionContext,
        "_WebHandlerDispatchContext": _WebHandlerDispatchContext,
        "_dispatch_get": _dispatch_get,
        "_dispatch_post": _dispatch_post,
        "_create_handler_class": _create_handler_class,
        "_route_for": _route_for,
        "_progress_update": _progress_update,
        "_run_simple_async_job_service": _run_simple_async_job_service,
        "_run_guided_job_service": _run_guided_job_service,
        "_run_job_service": _run_job_service,
        "_create_session_service": _create_session_service,
        "_web_session": _web_session,
        "_clear_brain_connection_verified_service": _clear_brain_connection_verified_service,
        "_csrf_for_session_service": _csrf_for_session_service,
        "_expired_session_cookie_header_service": _expired_session_cookie_header_service,
        "_expire_session_service": _expire_session_service,
        "_header_hostname_service": _header_hostname_service,
        "_header_port_service": _header_port_service,
        "_mark_brain_connection_verified_service": _mark_brain_connection_verified_service,
        "_payload_with_brain_session_credentials_service": _payload_with_brain_session_credentials_service,
        "_session_status_service": _session_status_service,
        "_get_or_create_session_service": _get_or_create_session_service,
        "_has_valid_admin_token_service": _has_valid_admin_token_service,
        "_normalize_host_service": _normalize_host_service,
        "_parse_cookies_service": _parse_cookies_service,
        "_path_requires_session_service": _path_requires_session_service,
        "_prune_sessions_service": _prune_sessions_service,
        "_remote_admin_required_service": _remote_admin_required_service,
        "_session_cookie_header_service": _session_cookie_header_service,
        "_stream_token_for_session_service": _stream_token_for_session_service,
        "_validate_session_service": _validate_session_service,
        "_validate_session_token_service": _validate_session_token_service,
        "_validate_stream_session_service": _validate_stream_session_service,
        "_content_security_policy_for_html": _content_security_policy_for_html,
        "_load_html": _load_html,
        "_render_html_service": _render_html_service,
        "_script_hash_sources_service": _script_hash_sources_service,
        "_style_hash_sources_service": _style_hash_sources_service,
        "_resolve_react_asset": _resolve_react_asset,
        "_safe_error_message_service": _safe_error_message_service,
        "_safe_error_payload_service": _safe_error_payload_service,
        "_web_error_payload_service": _web_error_payload_service,
        "_enrich_progress_service": _enrich_progress_service,
        "_find_free_port_service": _find_free_port_service,
        "_serve": _serve,
        "_shutdown_server_service": _shutdown_server_service,
        "_smoke_test_server_service": _smoke_test_server_service,
        "_active_auxiliary_operation_service": _active_auxiliary_operation_service,
        "_lifecycle_from_job_service": _lifecycle_from_job_service,
        "_load_check_results_service": _load_check_results_service,
        "_load_presets_service": _load_presets_service,
        "_match_preset_id_service": _match_preset_id_service,
        "_maybe_archive_lifecycle_service": _maybe_archive_lifecycle_service,
        "_WebSnapshotFacade": _WebSnapshotFacade,
        "_WebSnapshotRuntime": _WebSnapshotRuntime,
        "_DEFAULT_SESSION_TTL_SECONDS": _DEFAULT_SESSION_TTL_SECONDS,
        "_LOOPBACK_BIND_HOSTS": _LOOPBACK_BIND_HOSTS,
        "_SESSION_COOKIE_NAME": _SESSION_COOKIE_NAME,
        "_submit_batch_payload": _submit_batch_payload,
        "_submit_candidate_payload": _submit_candidate_payload,
        "live_submit_readiness_hard_gate": _live_submit_readiness_hard_gate,
        "_submission_preflight_block_service": _submission_preflight_block_service,
        "_submission_preflight_error_service": _submission_preflight_error_service,
        "_candidate_official_metrics_service": _candidate_official_metrics_service,
        "_candidate_official_metrics": _candidate_official_metrics_service,
        "_dedupe_cloud_alpha_rows_service": _dedupe_cloud_alpha_rows_service,
        "_extract_alpha_rows_service": _extract_alpha_rows_service,
        "_cloud_alpha_id_service": _cloud_alpha_id_service,
        "_cloud_row_sort_key_service": _cloud_row_sort_key_service,
        "_run_sync_job_service": _run_sync_job_service,
        "_sync_cloud_alphas_payload": _sync_cloud_alphas_payload,
        "_path_modified_at_service": _path_modified_at_service,
        "_official_context_file_counts_service": _official_context_file_counts_service,
        "_latest_cached_user_alphas_service": _latest_cached_user_alphas_service,
        "_latest_cached_user_alpha_path_service": _latest_cached_user_alpha_path_service,
        "_cached_user_alpha_paths_service": _cached_user_alpha_paths_service,
        "_save_official_context_json_service": _save_official_context_json_service,
        "_sqlite_expression_lookup_payload_service": _sqlite_expression_lookup_payload_service,
        "_sqlite_index_snapshot_service": _sqlite_index_snapshot_service,
        "_sqlite_record_lookup_payload_service": _sqlite_record_lookup_payload_service,
        "_CloudDefaults": _CloudDefaults,
        "_SnapshotDefaults": _SnapshotDefaults,
        "_WebDefaults": _WebDefaults,
    }
