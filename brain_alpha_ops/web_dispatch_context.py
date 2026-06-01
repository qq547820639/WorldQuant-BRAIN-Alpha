"""Context objects shared by web route dispatchers."""

from __future__ import annotations

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
