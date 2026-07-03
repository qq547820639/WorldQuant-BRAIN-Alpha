"""Web service namespace builder.

Consolidated from the former ``web_service_namespace/`` subpackage plus its
``web_service_namespace_imports`` sidecar. All aliased service names (each
``_``-prefixed) are bound into this module's namespace, and
``build_web_service_namespace`` assembles them into the legacy service
namespace dict consumed by ``brain_alpha_ops.web``.
"""
from __future__ import annotations

import brain_alpha_ops.web_html as _web_html  # noqa: F401
import brain_alpha_ops.web_session as _web_session  # noqa: F401
from brain_alpha_ops.brain_api.context_defaults import (  # noqa: F401
    DEFAULT_FIELDS as _DEFAULT_FIELDS,
    DEFAULT_OPERATORS as _DEFAULT_OPERATORS,
)
from brain_alpha_ops.config import (  # noqa: F401
    RunConfig as _RunConfig,
    load_run_config as _load_run_config,
    runtime_project_root as _runtime_project_root,
)
from brain_alpha_ops.jsonl import tail_text_lines as _tail_text_lines_service  # noqa: F401
from brain_alpha_ops.observability import error_payload as _error_payload  # noqa: F401
from brain_alpha_ops.research.observability import (  # noqa: F401
    build_research_observability_snapshot as _build_research_observability_snapshot,
)
from brain_alpha_ops.research.repository import (  # noqa: F401
    ResearchRepository as _ResearchRepository,
)
from brain_alpha_ops.research.safety import SubmissionLedger as _SubmissionLedger  # noqa: F401
from brain_alpha_ops.runner import (  # noqa: F401
    api_from_run_config as _api_from_run_config,
    run_pipeline_from_config as _run_pipeline_from_config,
)
from brain_alpha_ops.runtime_constants import (  # noqa: F401
    CloudDefaults as _CloudDefaults,
    SnapshotDefaults as _SnapshotDefaults,
    WebDefaults as _WebDefaults,
)
from brain_alpha_ops.submission_readiness import (  # noqa: F401
    live_submit_readiness_hard_gate as _live_submit_readiness_hard_gate,
)
from brain_alpha_ops.task_executor import ThreadTaskExecutor as _ThreadTaskExecutor  # noqa: F401
from brain_alpha_ops.tasks import JobStore as _DurableJobStore  # noqa: F401
from brain_alpha_ops.web.handlers.sync import (  # noqa: F401
    active_job_payload as _active_job_payload,
    cloud_alpha_id as _cloud_alpha_id_service,
    cloud_row_sort_key as _cloud_row_sort_key_service,
    health_payload as _health_payload,
    job_status_payload as _job_status_payload,
    lifecycle_payload as _lifecycle_payload,
    presets_payload as _presets_payload,
    profile_payload as _profile_payload,
    run_sync_job_service as _run_sync_job_service,
    sync_cloud_alphas_payload as _sync_cloud_alphas_payload,
)
from brain_alpha_ops.web.dispatch.web_post_handlers import (  # noqa: F401
    assistant_response_guidance_post_payload as _assistant_response_guidance_post_payload,
    assistant_response_parse_post_payload as _assistant_response_parse_post_payload,
    background_job_start_payload as _background_job_start_payload,
)
from brain_alpha_ops.web_async_jobs import (  # noqa: F401
    progress_update as _progress_update,
    run_simple_async_job_service as _run_simple_async_job_service,
)
from brain_alpha_ops.web_candidates.check import (  # noqa: F401
    check_candidate_payload as _check_candidate_payload,
)
from brain_alpha_ops.web_candidates.generation import (  # noqa: F401
    generate_candidates_payload as _generate_candidates_payload,
)
from brain_alpha_ops.web_candidates.selection import (  # noqa: F401
    is_passed_candidate_for_check as _is_passed_candidate_for_check,
    official_alpha_id as _official_alpha_id,
)
from brain_alpha_ops.web_check_availability import (  # noqa: F401
    check_candidate_availability as _check_candidate_availability,
    cloud_row_expression as _cloud_row_expression,
    cloud_similarity_risk as _cloud_similarity_risk,
    cloud_status_for as _cloud_status_for,
    run_check_batch_job_service as _run_check_batch_job_service,
)
from brain_alpha_ops.web_cloud_context_refresh import (  # noqa: F401
    refresh_cloud_context_for_check_service as _refresh_cloud_context_for_check_service,
)
from brain_alpha_ops.web_cloud.snapshot import (  # noqa: F401
    cloud_alpha_cache_probe as _cloud_alpha_cache_probe_service,
    cloud_alpha_snapshot as _cloud_alpha_snapshot_service,
    cloud_alpha_summary as _cloud_alpha_summary_service,
    persist_official_context as _persist_official_context_service,
    read_official_context_json as _read_official_context_json_service,
    read_official_context_metadata as _read_official_context_metadata_service,
    read_storage_jsonl as _read_storage_jsonl_service,
    read_storage_jsonl_stats as _read_storage_jsonl_stats_service,
    storage_jsonl_path as _storage_jsonl_path_service,
)
from brain_alpha_ops.web_config import (  # noqa: F401
    _MAX_BACKTEST_BATCH_SIZE,
    _MAX_CANDIDATES,
    _MAX_CONCURRENT_SIMULATIONS,
    _MAX_CYCLE_PAUSE_SECONDS,
    _MAX_CYCLES,
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
from brain_alpha_ops.web_config_schema import (  # noqa: F401
    public_config_schema as _public_config_schema,
)
from brain_alpha_ops.web_dispatch_context import (  # noqa: F401
    WebDispatchActionContext as _WebDispatchActionContext,
    WebDispatchAssistantContext as _WebDispatchAssistantContext,
    WebDispatchConfigContext as _WebDispatchConfigContext,
    WebDispatchCoreContext as _WebDispatchCoreContext,
    WebDispatchJobContext as _WebDispatchJobContext,
    WebDispatchResearchContext as _WebDispatchResearchContext,
    WebDispatchSessionContext as _WebDispatchSessionContext,
    WebHandlerDispatchContext as _WebHandlerDispatchContext,
)
from brain_alpha_ops.web_errors import (  # noqa: F401
    safe_error_message as _safe_error_message_service,
    safe_error_payload as _safe_error_payload_service,
    web_error_payload as _web_error_payload_service,
)
from brain_alpha_ops.web.dispatch.web_handler_dispatch import (  # noqa: F401
    dispatch_get as _dispatch_get,
    dispatch_post as _dispatch_post,
    stop_job_payload as _stop_job_payload,
)
from brain_alpha_ops.web_html import (  # noqa: F401
    content_security_policy_for_html as _content_security_policy_for_html,
    content_security_policy_for_html as _content_security_policy_for_html_service,
    load_html as _load_html,
    load_html as _load_html_service,
    render_html as _render_html_service,
    resolve_react_asset as _resolve_react_asset,
    resolve_react_asset as _resolve_react_asset_service,
    script_hash_sources as _script_hash_sources_service,
    style_hash_sources as _style_hash_sources_service,
)
from brain_alpha_ops.web_http_handler import (  # noqa: F401
    create_handler_class as _create_handler_class,
)
from brain_alpha_ops.web_job_registry import WebJobRegistry as _WebJobRegistry  # noqa: F401
from brain_alpha_ops.web_progress import enrich_progress as _enrich_progress_service  # noqa: F401
from brain_alpha_ops.web_rate_limit import RequestRateLimiter as _RequestRateLimiter  # noqa: F401
from brain_alpha_ops.web.dispatch.web_routes import route_for as _route_for  # noqa: F401
from brain_alpha_ops.web_run_job import (  # noqa: F401
    run_guided_job_service as _run_guided_job_service,
    run_job_service as _run_job_service,
)
from brain_alpha_ops.web_runtime_facade import (  # noqa: F401
    compute_run_stats as _compute_run_stats_service,
    status_category as _status_category_service,
)
from brain_alpha_ops.web_runtime_state import (  # noqa: F401
    active_auxiliary_operation as _active_auxiliary_operation_service,
    lifecycle_from_job as _lifecycle_from_job_service,
    load_check_results as _load_check_results_service,
    load_presets as _load_presets_service,
    match_preset_id as _match_preset_id_service,
    maybe_archive_lifecycle as _maybe_archive_lifecycle_service,
)
from brain_alpha_ops.web_security import (  # noqa: F401
    DEFAULT_SESSION_TTL_SECONDS as _DEFAULT_SESSION_TTL_SECONDS,
    LOOPBACK_BIND_HOSTS as _LOOPBACK_BIND_HOSTS,
    SESSION_COOKIE_NAME as _SESSION_COOKIE_NAME,
)
from brain_alpha_ops.web_server_lifecycle import (  # noqa: F401
    find_free_port as _find_free_port_service,
    serve as _serve,
    shutdown_server as _shutdown_server_service,
    smoke_test_server as _smoke_test_server_service,
)
from brain_alpha_ops.web_session import (  # noqa: F401
    clear_brain_connection_verified as _clear_brain_connection_verified_service,
    create_session as _create_session_service,
    csrf_for_session as _csrf_for_session_service,
    expire_session as _expire_session_service,
    expired_session_cookie_header as _expired_session_cookie_header_service,
    get_or_create_session as _get_or_create_session_service,
    has_valid_admin_token as _has_valid_admin_token_service,
    header_hostname as _header_hostname_service,
    header_port as _header_port_service,
    mark_brain_connection_verified as _mark_brain_connection_verified_service,
    normalize_host as _normalize_host_service,
    parse_cookies as _parse_cookies_service,
    path_requires_session as _path_requires_session_service,
    payload_with_brain_session_credentials as _payload_with_brain_session_credentials_service,
    prune_sessions as _prune_sessions_service,
    remote_admin_required as _remote_admin_required_service,
    session_cookie_header as _session_cookie_header_service,
    session_end_payload as _session_end_payload,
    session_status as _session_status_service,
    stream_token_for_session as _stream_token_for_session_service,
    validate_session as _validate_session_service,
    validate_session_token as _validate_session_token_service,
    validate_stream_session as _validate_stream_session_service,
)
from brain_alpha_ops.web_snapshot_facade import (  # noqa: F401
    WebSnapshotFacade as _WebSnapshotFacade,
)
from brain_alpha_ops.web_snapshot_runtime import (  # noqa: F401
    WebSnapshotRuntime as _WebSnapshotRuntime,
)
from brain_alpha_ops.web_sqlite_indexes import (  # noqa: F401
    sqlite_expression_lookup_payload as _sqlite_expression_lookup_payload_service,
    sqlite_index_snapshot as _sqlite_index_snapshot_service,
    sqlite_record_lookup_payload as _sqlite_record_lookup_payload_service,
)
from brain_alpha_ops.web_submission_batch import (  # noqa: F401
    submit_batch_payload as _submit_batch_payload,
)
from brain_alpha_ops.web_submission_safety import (  # noqa: F401
    candidate_official_metrics as _candidate_official_metrics_service,
    dedupe_cloud_alpha_rows as _dedupe_cloud_alpha_rows_service,
    extract_alpha_rows as _extract_alpha_rows_service,
    save_assistant_guidance_post_payload as _save_assistant_guidance_post_payload,
    submission_preflight_block as _submission_preflight_block_service,
    submission_preflight_error_message as _submission_preflight_error_service,
)
from brain_alpha_ops.web_submission_single import (  # noqa: F401
    submit_candidate_payload as _submit_candidate_payload,
)
from brain_alpha_ops.web_cloud.sync_job import (  # noqa: F401
    path_modified_at as _path_modified_at_service,
)
from brain_alpha_ops.web_cloud.sync_payload import (  # noqa: F401
    cached_user_alpha_paths as _cached_user_alpha_paths_service,
    connection_test_post_payload as _connection_test_post_payload,
    latest_cached_user_alpha_path as _latest_cached_user_alpha_path_service,
    latest_cached_user_alphas as _latest_cached_user_alphas_service,
    official_context_file_counts as _official_context_file_counts_service,
    save_official_context_json as _save_official_context_json_service,
)


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
        "_cloud_alpha_cache_probe_service": _cloud_alpha_cache_probe_service,
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


__all__ = [name for name in dir() if not name.startswith("__")]
