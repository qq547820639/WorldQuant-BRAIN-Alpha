"""Context objects shared by web route dispatchers.

Frozen dataclasses grouping related dispatch callbacks/services, plus the
registry mapping group names to their dataclass types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class WebDispatchCoreContext:
    route_for: Callable[[str, str], Any]
    web_error: Callable[[Exception, str], dict[str, Any]]
    payload_truthy: Callable[[Any], bool]
    bounded_query_int: Callable[[Any, int, int], int]
    bounded_query_float: Callable[[Any, float, float], float]
    rate_limit_request: Callable[[str, str, str], dict[str, Any]]
    safe_error_message: Callable[[Exception], str]
    error_payload: Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class WebDispatchSessionContext:
    remote_admin_required: Callable[[], bool]
    has_valid_admin_token: Callable[[Any], bool]
    get_or_create_session: Callable[[str], tuple[str, str]]
    stream_token_for_session: Callable[[str], str]
    session_cookie_header: Callable[[str], str]
    session_status: Callable[[str], dict[str, Any]]
    mark_brain_connection_verified: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]]
    clear_brain_connection_verified: Callable[[str], dict[str, Any]]
    payload_with_brain_session_credentials: Callable[[str, dict[str, Any]], dict[str, Any]]
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
    run_simple_async_job_service: Callable[..., None]


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
    run_config_from_payload: Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class WebDispatchResearchContext:
    latest_result_snapshot: Callable[[], dict[str, Any]]
    lifecycle_from_job: Callable[[dict[str, Any]], list[dict[str, Any]]]
    alpha_lifecycle_history: Callable[..., dict[str, Any]]
    cloud_alpha_snapshot: Callable[..., dict[str, Any]]
    official_context_file_counts: Callable[[], dict[str, Any]]
    research_memory_snapshot: Callable[..., dict[str, Any]]
    research_knowledge_snapshot: Callable[..., dict[str, Any]]
    research_observability_snapshot: Callable[..., dict[str, Any]]
    prompt_run_ledger_snapshot: Callable[..., dict[str, Any]]
    sqlite_index_snapshot: Callable[..., dict[str, Any]]
    sqlite_expression_lookup_payload: Callable[..., dict[str, Any]]
    sqlite_record_lookup_payload: Callable[..., dict[str, Any]]
    load_check_results: Callable[[], dict[str, Any]]
    user_profile_snapshot: Callable[[], dict[str, Any]]
    cloud_alpha_cache_probe: Callable[..., dict[str, Any]] | None = None
    candidate_summary_probe: Callable[[], dict[str, Any] | None] | None = None


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
