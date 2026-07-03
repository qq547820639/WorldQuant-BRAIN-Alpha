"""Web facade binding builder.

Consolidated from the former ``web_facade_bindings/`` subpackage. Hosts both
the consolidated import group (merged from the former
``_candidate_imports.py`` / ``_runtime_imports.py`` / ``_snapshot_imports.py``)
and ``build_web_facade_bindings`` which assembles the runtime namespace
dictionary consumed by ``brain_alpha_ops.web``.

Each aliased name (all ``_``-prefixed) is bound into this module's namespace
so that ``build_web_facade_bindings`` can reference them directly.

Also hosts the runtime compatibility surface (consolidated from
``web_runtime_bindings.py``): the ``serve()`` wrapper that boots the
watchdog sweep thread, plus the watchdog helpers themselves.  The
non-aliased bindings names remain available via the star import so the
``web_runtime_bindings`` bridge alias keeps resolving.
"""
from __future__ import annotations

import threading

from brain_alpha_ops.runtime_constants import WebDefaults as _WebDefaults
from brain_alpha_ops.web_candidates.bindings import *  # noqa: F401,F403
from brain_alpha_ops.web_candidates.bindings import (  # noqa: F401
    candidate_from_payload as _candidate_from_payload,
    check_candidate as _check_candidate,
    check_candidate_availability as _check_candidate_availability,
    cloud_similarity_risk as _cloud_similarity_risk,
    cloud_status_for as _cloud_status_for,
    datasets_from_fields as _datasets_from_fields,
    generate_candidates_payload as _generate_candidates_payload,
    load_check_results as _load_check_results,
    observability_submission_preflight as _observability_submission_preflight,
    passed_candidates_from_payload as _passed_candidates_from_payload,
    persist_official_context as _persist_official_context,
    record_submit_blocked as _record_submit_blocked,
    refresh_cloud_context_for_check as _refresh_cloud_context_for_check,
    run_check_batch_job as _run_check_batch_job,
    run_generate_candidates_job as _run_generate_candidates_job,
    run_scoring_evaluate_job as _run_scoring_evaluate_job,
    run_submit_batch_job as _run_submit_batch_job,
    run_sync_job as _run_sync_job,
    save_official_context_json as _save_official_context_json,
    submission_preflight_advisory as _submission_preflight_advisory,
    submission_preflight_error_message as _submission_preflight_error,
    submit_batch as _submit_batch,
    submit_candidate as _submit_candidate,
    sync_cloud_alphas as _sync_cloud_alphas,
)
from brain_alpha_ops.web_candidates.bindings import (  # noqa: F401
    alpha_lifecycle_history as _alpha_lifecycle_history,
    compute_run_stats as _compute_run_stats,
    find_free_port as _find_free_port,
    handler_dispatch_context as _handler_dispatch_context,
    lifecycle_from_job as _lifecycle_from_job,
    lookup_sse_job as _lookup_sse_job,
    main as _main,
    maybe_archive_lifecycle as _maybe_archive_lifecycle,
    run_job as _run_job,
    shutdown_server as _shutdown_server,
    smoke_test_server as _smoke_test_server,
    test_connection as _test_connection,
)
from brain_alpha_ops.web_candidates.selection import (  # noqa: F401
    candidate_from_payload as _candidate_from_payload_service,
    passed_candidates_from_payload as _passed_candidates_from_payload_service,
)
from brain_alpha_ops.web_submission_safety import (  # noqa: F401
    observability_submission_preflight as _observability_submission_preflight_service,
    record_submit_blocked_event as _record_submit_blocked_event_service,
    submission_preflight_advisory as _submission_preflight_advisory_service,
)
from brain_alpha_ops.web_config_bindings import (  # noqa: F401
    config_from_payload as _config_from_payload,
    load_run_config_provider as _load_run_config_provider,
    run_config_from_payload as _run_config_from_payload,
    runtime_project_root_provider as _runtime_project_root_provider,
    save_run_config_payload as _save_run_config_payload,
)
from brain_alpha_ops.web_job_bindings import (  # noqa: F401
    active_auxiliary_operation as _active_auxiliary_operation,
    job_registry as _job_registry,
    job_registry_view as _job_registry_view,
    rate_limit_request as _rate_limit_request,
    submit_background_job as _submit_background_job,
)
from brain_alpha_ops.web_session_bindings import (  # noqa: F401
    configure_session_policy as _configure_session_policy,
    normalize_host as _normalize_host,
)
from brain_alpha_ops.web_snapshot_bindings import (  # noqa: F401
    anti_overfit_snapshot as _anti_overfit_snapshot,
    assistant_context_snapshot as _assistant_context_snapshot,
    assistant_cross_review_payload as _assistant_cross_review_payload,
    assistant_guidance_history as _assistant_guidance_history,
    assistant_guidance_snapshot as _assistant_guidance_snapshot,
    assistant_request_snapshot as _assistant_request_snapshot,
    assistant_response_guidance_payload as _assistant_response_guidance_payload,
    assistant_response_parse_payload as _assistant_response_parse_payload,
    cached_user_alpha_paths as _cached_user_alpha_paths,
    cloud_alpha_cache_probe as _cloud_alpha_cache_probe,
    cloud_alpha_snapshot as _cloud_alpha_snapshot,
    cloud_alpha_summary as _cloud_alpha_summary,
    durable_job_rows as _durable_job_rows,
    latest_cached_user_alpha_path as _latest_cached_user_alpha_path,
    latest_cached_user_alphas as _latest_cached_user_alphas,
    latest_result_snapshot as _latest_result_snapshot,
    latest_run_history_path as _latest_run_history_path,
    load_presets as _load_presets,
    match_preset_id as _match_preset_id,
    official_context_file_counts as _official_context_file_counts,
    prompt_run_ledger_snapshot as _prompt_run_ledger_snapshot,
    public_run_config as _public_run_config,
    read_official_context_json as _read_official_context_json,
    read_official_context_metadata as _read_official_context_metadata,
    read_storage_jsonl as _read_storage_jsonl,
    read_storage_jsonl_stats as _read_storage_jsonl_stats,
    research_knowledge_snapshot as _research_knowledge_snapshot,
    research_memory_snapshot as _research_memory_snapshot,
    research_observability_snapshot as _research_observability_snapshot,
    rolling_validation_snapshot as _rolling_validation_snapshot,
    save_assistant_guidance_payload as _save_assistant_guidance_payload,
    snapshot_facade as _snapshot_facade,
    snapshot_runtime as _snapshot_runtime,
    sqlite_expression_lookup_payload as _sqlite_expression_lookup_payload,
    sqlite_index_snapshot as _sqlite_index_snapshot,
    sqlite_record_lookup_payload as _sqlite_record_lookup_payload,
    storage_jsonl_path as _storage_jsonl_path,
    user_profile_snapshot as _user_profile_snapshot,
)


# ═══════════════════════ Runtime serve wrapper + watchdog ═══════════════════


def serve(
    port=None,
    open_browser=True,
    host=_WebDefaults.HOST,
    session_ttl_seconds=None,
    allow_multiple_sessions=None,
    allow_remote=False,
    secure_cookies=None,
):
    from brain_alpha_ops import web

    url = web._runtime_facade.serve(
        web._app_context(),
        port=port,
        open_browser=open_browser,
        host=host,
        session_ttl_seconds=session_ttl_seconds,
        allow_multiple_sessions=allow_multiple_sessions,
        allow_remote=allow_remote,
        secure_cookies=secure_cookies,
    )
    _start_watchdog_sweep_thread(web)
    return url


_serve = serve


def _start_watchdog_sweep_thread(web) -> None:
    stop_event = getattr(web, "SERVER_STOP", None)
    if stop_event is None:
        return
    existing = getattr(web, "_WATCHDOG_SWEEP_THREAD", None)
    if existing is not None and existing.is_alive():
        return
    thread = threading.Thread(target=_watchdog_sweep_loop, args=(web, stop_event), daemon=True)
    setattr(web, "_WATCHDOG_SWEEP_THREAD", thread)
    thread.start()


def _watchdog_sweep_loop(web, stop_event) -> None:
    interval = _watchdog_sweep_interval(web)
    while not stop_event.wait(interval):
        _watchdog_sweep_once(web)


def _watchdog_sweep_interval(web) -> float:
    timeouts: list[float] = []
    for store in _watchdog_stores(web):
        try:
            timeout = float(getattr(store, "watchdog_timeout_seconds", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if timeout > 0:
            timeouts.append(timeout)
    if not timeouts:
        return 30.0
    return max(5.0, min(30.0, min(timeouts) / 2.0))


def _watchdog_sweep_once(web) -> int:
    changed = 0
    for store in _watchdog_stores(web):
        sweep = getattr(store, "watchdog_sweep", None)
        if not callable(sweep):
            continue
        changed += int(sweep() or 0)
    return changed


def _watchdog_stores(web) -> tuple[object, ...]:
    return tuple(
        store
        for store in (
            getattr(web, "JOBS", None),
            getattr(web, "SYNC_JOBS", None),
            getattr(web, "CHECK_JOBS", None),
            getattr(web, "ASYNC_JOBS", None),
        )
        if store is not None
    )


# ═══════════════════════ Facade binding builder ═════════════════════════════


def build_web_facade_bindings(namespace):
    web_defaults = namespace["_WebDefaults"]
    cloud_defaults = namespace["_CloudDefaults"]
    web_session = namespace["_web_session"]
    web_html = namespace["_web_html"]
    job_registry_obj = namespace["_WebJobRegistry"].create(namespace["_runtime_project_root"](), max_workers=4)
    result = {
        "HOST": web_defaults.HOST,
        "DEFAULT_PORT": web_defaults.PORT,
        "CLOUD_SYNC_STALE_SECONDS": cloud_defaults.CLOUD_SYNC_STALE_SECONDS,
        "SESSION_TTL_SECONDS": namespace.get("_DEFAULT_SESSION_TTL_SECONDS", 3600),
        "SESSION_ALLOW_MULTIPLE": True,
        "_MAX_CANDIDATES": namespace["_MAX_CANDIDATES"],
        "_MAX_VALIDATIONS": namespace["_MAX_VALIDATIONS"],
        "_MAX_SIMULATIONS": namespace["_MAX_SIMULATIONS"],
        "_MAX_CONCURRENT_SIMULATIONS": namespace["_MAX_CONCURRENT_SIMULATIONS"],
        "_MAX_POOL_SIZE": namespace["_MAX_POOL_SIZE"],
        "_MAX_CYCLES": namespace["_MAX_CYCLES"],
        "_MAX_CYCLE_PAUSE_SECONDS": namespace["_MAX_CYCLE_PAUSE_SECONDS"],
        "_MAX_BACKTEST_BATCH_SIZE": namespace["_MAX_BACKTEST_BATCH_SIZE"],
        "SESSION_MANAGER": web_session.SESSION_MANAGER,
        "SESSIONS": web_session.SESSIONS,
        "SESSION_LOCK": web_session.SESSION_LOCK,
        "HTML": "",
        "_HTML_CACHE": "",
        "_load_run_config_provider": _load_run_config_provider,
        "_runtime_project_root_provider": _runtime_project_root_provider,
        "_header_hostname": namespace["_header_hostname_service"],
        "_header_port": namespace["_header_port_service"],
        "_path_requires_session": namespace["_path_requires_session_service"],
        "configure_session_policy": _configure_session_policy,
        "_parse_cookies": namespace["_parse_cookies_service"],
        "_session_cookie_header": web_session.session_cookie_header,
        "_expired_session_cookie_header": web_session.expired_session_cookie_header,
        "_prune_sessions": web_session.prune_sessions,
        "_create_session": web_session.create_session,
        "_expire_session": web_session.expire_session,
        "_validate_session_token": web_session.validate_session_token,
        "_validate_session": web_session.validate_session,
        "_validate_stream_session": web_session.validate_stream_session,
        "_csrf_for_session": web_session.csrf_for_session,
        "_stream_token_for_session": web_session.stream_token_for_session,
        "_get_or_create_session": web_session.get_or_create_session,
        "_session_status": web_session.session_status,
        "_mark_brain_connection_verified": web_session.mark_brain_connection_verified,
        "_clear_brain_connection_verified": web_session.clear_brain_connection_verified,
        "_payload_with_brain_session_credentials": web_session.payload_with_brain_session_credentials,
        "_remote_admin_required": web_session.remote_admin_required,
        "_has_valid_admin_token": web_session.has_valid_admin_token,
        "safe_error_message": namespace["_safe_error_message_service"],
        "safe_error_payload": namespace["_safe_error_payload_service"],
        "_web_error": namespace["_web_error_payload_service"],
        "_load_html": web_html.load_html,
        "_render_html": web_html.render_html,
        "_script_hash_sources": web_html.script_hash_sources,
        "_style_hash_sources": web_html.style_hash_sources,
        "content_security_policy_for_html": web_html.content_security_policy_for_html,
        "run_config_from_payload": _run_config_from_payload,
        "config_from_payload": _config_from_payload,
        "save_run_config_payload": _save_run_config_payload,
        "test_connection": _test_connection,
        "_enrich_progress": namespace["_enrich_progress_service"],
        "JOB_REGISTRY": job_registry_obj,
        "SERVER_LOCK": threading.Lock(),
        "SERVER": None,
        "SERVER_STOP": threading.Event(),
        "job_registry": _job_registry,
        "_job_registry_view": _job_registry_view,
        "active_auxiliary_operation": _active_auxiliary_operation,
        "rate_limit_request": _rate_limit_request,
        "normalize_host": _normalize_host,
        "_start_thread": lambda target, *a: threading.Thread(target=target, args=a, daemon=True).start(),
        "_submit_background_job": _submit_background_job,
        "_handler_dispatch_context": _handler_dispatch_context,
        "_lookup_sse_job": _lookup_sse_job,
        "Handler": namespace["_create_handler_class"](
            server_version=web_defaults.SERVER_VERSION,
            max_body_bytes=web_defaults.MAX_BODY_BYTES,
            dispatch_get=namespace["_dispatch_get"],
            dispatch_post=namespace["_dispatch_post"],
            dispatch_context=_handler_dispatch_context,
            web_session=web_session,
            jobs=job_registry_obj.jobs,
            resolve_sse_job=_lookup_sse_job,
            enrich_progress=namespace["_enrich_progress_service"],
            content_security_policy_for_html=web_html.content_security_policy_for_html,
            sse_push_interval=web_defaults.SSE_PUSH_INTERVAL,
            max_sse_duration=web_defaults.MAX_SSE_DURATION,
            resolve_static_asset=web_html.resolve_react_asset,
        ),
        "run_job": _run_job,
        "_compute_run_stats": _compute_run_stats,
        "generate_candidates_payload": _generate_candidates_payload,
        "run_generate_candidates_job": _run_generate_candidates_job,
        "run_scoring_evaluate_job": _run_scoring_evaluate_job,
        "run_submit_batch_job": _run_submit_batch_job,
        "lifecycle_from_job": _lifecycle_from_job,
        "alpha_lifecycle_history": _alpha_lifecycle_history,
        "_LAST_ARCHIVE_CHECK": 0.0,
        "_ARCHIVE_CHECK_INTERVAL": 3600.0,
        "_maybe_archive_lifecycle": _maybe_archive_lifecycle,
        "_status_category": namespace["_status_category_service"],
        "cloud_alpha_snapshot": _cloud_alpha_snapshot,
        "cloud_alpha_cache_probe": _cloud_alpha_cache_probe,
        "_snapshot_runtime": _snapshot_runtime,
        "_snapshot_facade": _snapshot_facade,
        "research_memory_snapshot": _research_memory_snapshot,
        "research_knowledge_snapshot": _research_knowledge_snapshot,
        "research_observability_snapshot": _research_observability_snapshot,
        "prompt_run_ledger_snapshot": _prompt_run_ledger_snapshot,
        "sqlite_index_snapshot": _sqlite_index_snapshot,
        "sqlite_expression_lookup_payload": _sqlite_expression_lookup_payload,
        "sqlite_record_lookup_payload": _sqlite_record_lookup_payload,
        "_durable_job_rows": _durable_job_rows,
        "assistant_guidance_snapshot": _assistant_guidance_snapshot,
        "_assistant_guidance_history": _assistant_guidance_history,
        "assistant_context_snapshot": _assistant_context_snapshot,
        "assistant_request_snapshot": _assistant_request_snapshot,
        "assistant_response_parse_payload": _assistant_response_parse_payload,
        "assistant_response_guidance_payload": _assistant_response_guidance_payload,
        "anti_overfit_snapshot": _anti_overfit_snapshot,
        "rolling_validation_snapshot": _rolling_validation_snapshot,
        "assistant_cross_review_payload": _assistant_cross_review_payload,
        "save_assistant_guidance_payload": _save_assistant_guidance_payload,
        "latest_result_snapshot": _latest_result_snapshot,
        "_latest_run_history_path": _latest_run_history_path,
        "_user_profile_snapshot": _user_profile_snapshot,
        "_load_presets": _load_presets,
        "_match_preset_id": _match_preset_id,
        "_dedupe_cloud_alpha_rows": namespace["_dedupe_cloud_alpha_rows_service"],
        "_latest_cached_user_alphas": _latest_cached_user_alphas,
        "_latest_cached_user_alpha_path": _latest_cached_user_alpha_path,
        "_cached_user_alpha_paths": _cached_user_alpha_paths,
        "_path_modified_at": namespace["_path_modified_at_service"],
        "_extract_alpha_rows": namespace["_extract_alpha_rows_service"],
        "_official_context_file_counts": _official_context_file_counts,
        "_read_official_context_metadata": _read_official_context_metadata,
        "_read_official_context_json": _read_official_context_json,
        "_cloud_alpha_summary": _cloud_alpha_summary,
        "_cloud_alpha_id": namespace["_cloud_alpha_id_service"],
        "_cloud_row_sort_key": namespace["_cloud_row_sort_key_service"],
        "_candidate_from_payload": _candidate_from_payload_service,
        "candidate_from_payload": _candidate_from_payload,
        "sync_cloud_alphas": _sync_cloud_alphas,
        "run_sync_job": _run_sync_job,
        "run_check_batch_job": _run_check_batch_job,
        "refresh_cloud_context_for_check": _refresh_cloud_context_for_check,
        "_datasets_from_fields": _datasets_from_fields,
        "_persist_official_context": _persist_official_context,
        "_save_official_context_json": _save_official_context_json,
        "_passed_candidates_from_payload": _passed_candidates_from_payload_service,
        "passed_candidates_from_payload": _passed_candidates_from_payload,
        "check_candidate_availability": _check_candidate_availability,
        "cloud_status_for": _cloud_status_for,
        "cloud_similarity_risk": _cloud_similarity_risk,
        "check_candidate": _check_candidate,
        "submission_preflight_error": _submission_preflight_error,
        "_submit_preflight_block": namespace["_submission_preflight_block_service"],
        "_submission_preflight_advisory": _submission_preflight_advisory_service,
        "submission_preflight_advisory": _submission_preflight_advisory,
        "_observability_submission_preflight": _observability_submission_preflight_service,
        "observability_submission_preflight": _observability_submission_preflight,
        "cloud_row_expression": namespace["_cloud_row_expression"],
        "_record_submit_blocked_event": _record_submit_blocked_event_service,
        "record_submit_blocked": _record_submit_blocked,
        "submit_candidate": _submit_candidate,
        "load_check_results": _load_check_results,
        "submit_batch": _submit_batch,
        "_storage_jsonl_path": _storage_jsonl_path,
        "_read_storage_jsonl": _read_storage_jsonl,
        "_read_storage_jsonl_stats": _read_storage_jsonl_stats,
        "_tail_text_lines": namespace["_tail_text_lines_service"],
        "public_run_config": _public_run_config,
        "find_free_port": _find_free_port,
        "shutdown_server": _shutdown_server,
        "serve": _serve,
        "smoke_test_server": _smoke_test_server,
        "main": _main,
    }
    return result


__all__ = ["build_web_facade_bindings", "serve"]
