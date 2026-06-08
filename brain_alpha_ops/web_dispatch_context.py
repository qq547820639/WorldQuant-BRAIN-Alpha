"""Web application context and dispatch context types."""

from __future__ import annotations

WEB_CONTEXT_ALLOWED_NAMES = frozenset({
    "ASYNC_JOBS",
    "CHECK_JOBS",
    "CLOUD_SYNC_STALE_SECONDS",
    "DEFAULT_FIELDS",
    "DEFAULT_OPERATORS",
    "DEFAULT_PORT",
    "HOST",
    "Handler",
    "JOB_REGISTRY",
    "JOBS",
    "LOOPBACK_BIND_HOSTS",
    "RATE_LIMITER",
    "ResearchRepository",
    "SERVER",
    "SERVER_STOP",
    "SESSION_COOKIE_NAME",
    "SUBMIT_LOCK",
    "SYNC_JOBS",
    "SubmissionLedger",
    "TASK_EXECUTOR",
    "WebDispatchActionContext",
    "WebDispatchAssistantContext",
    "WebDispatchConfigContext",
    "WebDispatchCoreContext",
    "WebDispatchJobContext",
    "WebDispatchResearchContext",
    "WebDispatchSessionContext",
    "WebHandlerDispatchContext",
    "WebSnapshotFacade",
    "WebSnapshotRuntime",
    "_ARCHIVE_CHECK_INTERVAL",
    "_LAST_ARCHIVE_CHECK",
    "_bounded_query_float",
    "_bounded_query_int",
    "_candidate_from_payload",
    "_check_candidate_availability",
    "_cloud_alpha_snapshot_service",
    "_cloud_similarity_risk",
    "_cloud_status_for",
    "_compute_run_stats",
    "_csrf_for_session",
    "_datasets_from_fields",
    "_datasets_from_fields_service",
    "_enrich_progress",
    "_expire_session",
    "_expired_session_cookie_header",
    "_find_free_port_service",
    "_generate_candidates_payload",
    "_get_or_create_session",
    "_has_valid_admin_token",
    "_latest_run_history_path",
    "_lifecycle_from_job_service",
    "_load_check_results_service",
    "_load_presets",
    "_load_presets_service",
    "_match_preset_id_service",
    "_maybe_archive_lifecycle_service",
    "_observability_submission_preflight",
    "_official_context_file_counts",
    "_parse_cookies",
    "_passed_candidates_from_payload",
    "_persist_official_context",
    "_persist_official_context_service",
    "_read_storage_jsonl",
    "_read_storage_jsonl_service",
    "_read_storage_jsonl_stats_service",
    "_record_submit_blocked_event",
    "_remote_admin_required",
    "_render_html",
    "_save_official_context_json_service",
    "_serve_service",
    "_session_cookie_header",
    "_shutdown_server_service",
    "_smoke_test_server_service",
    "_snapshot_facade",
    "_snapshot_runtime",
    "_start_thread",
    "_storage_jsonl_path",
    "_storage_jsonl_path_service",
    "_stream_token_for_session",
    "_submission_preflight_advisory",
    "_submission_preflight_error_message",
    "_submit_background_job",
    "_user_profile_snapshot",
    "_web_error",
    "active_auxiliary_operation",
    "active_job_payload",
    "anti_overfit_snapshot",
    "api_from_run_config",
    "assistant_context_snapshot",
    "assistant_cross_review_payload",
    "assistant_guidance_snapshot",
    "assistant_request_snapshot",
    "assistant_response_guidance_payload",
    "assistant_response_guidance_post_payload",
    "assistant_response_parse_payload",
    "assistant_response_parse_post_payload",
    "background_job_start_payload",
    "build_research_observability_snapshot",
    "candidate_from_payload",
    "check_candidate",
    "check_candidate_availability",
    "check_candidate_payload",
    "cloud_alpha_snapshot",
    "cloud_status_for",
    "config_from_payload",
    "configure_session_policy",
    "connection_test_post_payload",
    "error_payload",
    "generate_candidates_payload",
    "health_payload",
    "job_registry",
    "job_status_payload",
    "latest_result_snapshot",
    "lifecycle_from_job",
    "lifecycle_payload",
    "load_check_results",
    "load_run_config",
    "logger",
    "live_submit_readiness_hard_gate",
    "normalize_host",
    "observability_submission_preflight",
    "official_alpha_id",
    "passed_candidates_from_payload",
    "payload_truthy",
    "presets_payload",
    "profile_payload",
    "progress_update",
    "prompt_run_ledger_snapshot",
    "public_config_schema",
    "public_run_config",
    "rate_limit_request",
    "record_submit_blocked",
    "refresh_cloud_context_for_check",
    "refresh_cloud_context_for_check_service",
    "research_knowledge_snapshot",
    "research_memory_snapshot",
    "research_observability_snapshot",
    "rolling_validation_snapshot",
    "route_for",
    "run_check_batch_job",
    "run_check_batch_job_service",
    "run_config_from_payload",
    "run_generate_candidates_job",
    "run_guided_job_service",
    "run_job",
    "run_job_service",
    "run_pipeline_from_config",
    "run_scoring_evaluate_job",
    "run_simple_async_job_service",
    "run_submit_batch_job",
    "run_sync_job",
    "run_sync_job_service",
    "runtime_project_root",
    "safe_error_message",
    "save_assistant_guidance_payload",
    "save_assistant_guidance_post_payload",
    "save_run_config_payload",
    "serve",
    "session_end_payload",
    "shutdown_server",
    "smoke_test_server",
    "sqlite_expression_lookup_payload",
    "sqlite_index_snapshot",
    "sqlite_record_lookup_payload",
    "stop_job_payload",
    "submission_preflight_advisory",
    "submit_batch",
    "submit_batch_payload",
    "submit_candidate",
    "submit_candidate_payload",
    "sync_cloud_alphas_payload",
    "test_connection",
    "web_session",
})


class WebApplicationContext:
    """Runtime context facade for web console services."""

    __slots__ = ("_module", "_allowed_names")

    def __init__(self, module, *, allowed_names=WEB_CONTEXT_ALLOWED_NAMES):
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_allowed_names", frozenset(allowed_names))

    def __getattribute__(self, name: str):
        if name in {"_module", "_allowed_names"}:
            raise AttributeError(name)
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str):
        allowed_names = object.__getattribute__(self, "_allowed_names")
        if name not in allowed_names:
            raise AttributeError(name)
        module = object.__getattribute__(self, "_module")
        return getattr(module, name)

    def __setattr__(self, name: str, value) -> None:
        allowed_names = object.__getattribute__(self, "_allowed_names")
        if name not in allowed_names:
            raise AttributeError(name)
        module = object.__getattribute__(self, "_module")
        setattr(module, name, value)


"""Context objects shared by web route dispatchers."""

from dataclasses import dataclass, replace
from typing import Any, Callable


@dataclass(frozen=True)
class WebDispatchCoreContext:
    route_for: Callable[[str, str], Any]
    web_error: Callable[[Exception, str], dict[str, Any]]
    payload_truthy: Callable[[Any], bool]
    bounded_query_int: Callable[[Any, int, int], int]
    bounded_query_float: Callable[[Any, float, float], float]
    rate_limit_request: Callable[[str, str, str], dict[str, Any]]


@dataclass(frozen=True)
class WebDispatchSessionContext:
    remote_admin_required: Callable[[], bool]
    has_valid_admin_token: Callable[[Any], bool]
    get_or_create_session: Callable[[str], tuple[str, str]]
    stream_token_for_session: Callable[[str], str]
    session_cookie_header: Callable[[str], str]
    render_html: Callable[[str, str], str]
    session_end_payload: Callable[..., tuple[dict[str, Any], list[tuple[str, str]]]]
    expire_session: Callable[[str], None]
    expired_session_cookie_header: Callable[[], str]
    start_shutdown: Callable[[], None]


@dataclass(frozen=True)
class WebDispatchJobContext:
    job_status_payload: Callable[..., tuple[dict[str, Any], int]]
    active_job_payload: Callable[..., dict[str, Any]]
    lifecycle_payload: Callable[..., dict[str, Any]]
    jobs: Any
    sync_jobs: Any
    check_jobs: Any
    async_jobs: Any
    enrich_progress: Callable[[dict[str, Any]], dict[str, Any]]
    background_job_start_payload: Callable[..., tuple[dict[str, Any], int]]
    start_run_job: Callable[[str, dict[str, Any]], None]
    stop_job_payload: Callable[..., dict[str, Any]]
    active_auxiliary_operation: Callable[..., tuple[str, str] | None]


@dataclass(frozen=True)
class WebDispatchConfigContext:
    health_payload: Callable[[], dict[str, Any]]
    profile_payload: Callable[..., dict[str, Any]]
    presets_payload: Callable[..., dict[str, Any]]
    public_run_config: Callable[[], dict[str, Any]]
    public_config_schema: Callable[[], dict[str, Any]]
    save_run_config_payload: Callable[[dict[str, Any]], dict[str, Any]]
    connection_test_post_payload: Callable[..., dict[str, Any]]
    test_connection: Callable[[dict[str, Any]], dict[str, Any]]
    validate_run_payload: Callable[[dict[str, Any]], None]
    load_presets: Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class WebDispatchResearchContext:
    latest_result_snapshot: Callable[[], dict[str, Any]]
    lifecycle_from_job: Callable[[dict[str, Any]], list[dict[str, Any]]]
    cloud_alpha_snapshot: Callable[..., dict[str, Any]]
    research_memory_snapshot: Callable[..., dict[str, Any]]
    research_knowledge_snapshot: Callable[..., dict[str, Any]]
    research_observability_snapshot: Callable[..., dict[str, Any]]
    prompt_run_ledger_snapshot: Callable[..., dict[str, Any]]
    sqlite_index_snapshot: Callable[..., dict[str, Any]]
    sqlite_expression_lookup_payload: Callable[..., dict[str, Any]]
    sqlite_record_lookup_payload: Callable[..., dict[str, Any]]
    load_check_results: Callable[[], dict[str, Any]]
    user_profile_snapshot: Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class WebDispatchAssistantContext:
    assistant_context_snapshot: Callable[..., dict[str, Any]]
    assistant_guidance_snapshot: Callable[..., dict[str, Any]]
    assistant_request_snapshot: Callable[..., dict[str, Any]]
    anti_overfit_snapshot: Callable[..., dict[str, Any]]
    rolling_validation_snapshot: Callable[..., dict[str, Any]]
    assistant_response_parse_post_payload: Callable[..., dict[str, Any]]
    assistant_response_parse_payload: Callable[[dict[str, Any]], dict[str, Any]]
    assistant_response_guidance_post_payload: Callable[..., dict[str, Any]]
    assistant_response_guidance_payload: Callable[[dict[str, Any]], dict[str, Any]]
    assistant_cross_review_payload: Callable[[dict[str, Any]], dict[str, Any]]
    save_assistant_guidance_post_payload: Callable[..., dict[str, Any]]
    save_assistant_guidance_payload: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class WebDispatchActionContext:
    start_sync_job: Callable[[str, dict[str, Any]], None]
    check_candidate: Callable[[dict[str, Any]], dict[str, Any]]
    generate_candidates_payload: Callable[[dict[str, Any]], dict[str, Any]]
    start_generate_candidates_job: Callable[[str, dict[str, Any]], None]
    start_check_batch_job: Callable[[str, dict[str, Any]], None]
    start_scoring_evaluate_job: Callable[[str, dict[str, Any]], None]
    start_submit_batch_job: Callable[[str, dict[str, Any]], None]
    submit_lock: Any
    submit_candidate: Callable[[dict[str, Any]], dict[str, Any]]
    submit_batch: Callable[[dict[str, Any]], dict[str, Any]]


_CONTEXT_GROUPS = (
    "core",
    "session",
    "job",
    "config",
    "research",
    "assistant",
    "actions",
)
_GROUP_CLASSES = {
    "core": WebDispatchCoreContext,
    "session": WebDispatchSessionContext,
    "job": WebDispatchJobContext,
    "config": WebDispatchConfigContext,
    "research": WebDispatchResearchContext,
    "assistant": WebDispatchAssistantContext,
    "actions": WebDispatchActionContext,
}


@dataclass(frozen=True, init=False)
class WebHandlerDispatchContext:
    core: WebDispatchCoreContext
    session: WebDispatchSessionContext
    job: WebDispatchJobContext
    config: WebDispatchConfigContext
    research: WebDispatchResearchContext
    assistant: WebDispatchAssistantContext
    actions: WebDispatchActionContext

    def __init__(
        self,
        *,
        core: WebDispatchCoreContext | None = None,
        session: WebDispatchSessionContext | None = None,
        job: WebDispatchJobContext | None = None,
        config: WebDispatchConfigContext | None = None,
        research: WebDispatchResearchContext | None = None,
        assistant: WebDispatchAssistantContext | None = None,
        actions: WebDispatchActionContext | None = None,
        **flat: Any,
    ) -> None:
        provided = {
            "core": core,
            "session": session,
            "job": job,
            "config": config,
            "research": research,
            "assistant": assistant,
            "actions": actions,
        }
        remaining = dict(flat)
        for group_name, group in list(provided.items()):
            if group is not None and not isinstance(group, _GROUP_CLASSES[group_name]):
                remaining[group_name] = group
                provided[group_name] = None
        for group_name in _CONTEXT_GROUPS:
            group = provided[group_name]
            if group is None:
                group = _build_context_group(_GROUP_CLASSES[group_name], remaining)
            else:
                overrides = {}
                for field_name in _GROUP_CLASSES[group_name].__dataclass_fields__:
                    if field_name in remaining:
                        overrides[field_name] = remaining.pop(field_name)
                if overrides:
                    group = replace(group, **overrides)
            object.__setattr__(self, group_name, group)
        if remaining:
            unknown = ", ".join(sorted(remaining))
            raise TypeError(f"unknown WebHandlerDispatchContext fields: {unknown}")

    def __getattr__(self, name: str) -> Any:
        for group_name in _CONTEXT_GROUPS:
            group = object.__getattribute__(self, group_name)
            if name in getattr(group, "__dataclass_fields__", {}):
                return getattr(group, name)
        raise AttributeError(name)


def _build_context_group(group_class: type, values: dict[str, Any]) -> Any:
    fields = group_class.__dataclass_fields__
    payload = {}
    for name in fields:
        if name not in values:
            raise TypeError(f"missing WebHandlerDispatchContext field: {name}")
        payload[name] = values.pop(name)
    return group_class(**payload)
