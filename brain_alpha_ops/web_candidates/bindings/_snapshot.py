"""Web snapshot bindings for runtime, research, assistant and storage views."""

from __future__ import annotations

from ._helpers import _app_context, _runtime_facade, _snapshot_facade, _web


def cloud_alpha_snapshot(limit=None):
    return _runtime_facade().cloud_alpha_snapshot(_app_context(), limit=limit)


def cloud_alpha_cache_probe():
    return _runtime_facade().cloud_alpha_cache_probe(_app_context())


def snapshot_runtime():
    return _runtime_facade().snapshot_runtime(_app_context())


def snapshot_facade():
    return _runtime_facade().snapshot_facade(_app_context())


def research_memory_snapshot(*, limit=5000, top_n=10):
    return _snapshot_facade().research_memory_snapshot(limit=limit, top_n=top_n)


def research_knowledge_snapshot(*, limit=100, min_confidence=0.0):
    return _snapshot_facade().research_knowledge_snapshot(limit=limit, min_confidence=min_confidence)


def research_observability_snapshot(*, limit=5000, top_n=10, include_cloud=True):
    return _snapshot_facade().research_observability_snapshot(limit=limit, top_n=top_n, include_cloud=include_cloud)


def prompt_run_ledger_snapshot(*, limit=100):
    return _snapshot_facade().prompt_run_ledger_snapshot(limit=limit)


def sqlite_index_snapshot(*, top_n=10):
    web = _web()
    return web._sqlite_index_snapshot_service(
        top_n=top_n,
        load_config=web._load_run_config_provider(),
        web_error=web._web_error,
    )


def sqlite_expression_lookup_payload(*, expression, top_n=10, min_similarity=0.75, max_scan_rows=2000):
    web = _web()
    return web._sqlite_expression_lookup_payload_service(
        expression=expression,
        top_n=top_n,
        min_similarity=min_similarity,
        max_scan_rows=max_scan_rows,
        load_config=web._load_run_config_provider(),
        web_error=web._web_error,
    )


def sqlite_record_lookup_payload(*, alpha_id, limit=50):
    web = _web()
    return web._sqlite_record_lookup_payload_service(
        alpha_id=alpha_id,
        limit=limit,
        load_config=web._load_run_config_provider(),
        web_error=web._web_error,
    )


def durable_job_rows(*, limit):
    return _snapshot_facade().durable_job_rows(limit=limit)


def assistant_guidance_snapshot(*, limit=100, min_confidence=None):
    return _snapshot_facade().assistant_guidance_snapshot(limit=limit, min_confidence=min_confidence)


def assistant_guidance_history(rows, *, min_confidence, scoring_policy=None, outcomes_by_guidance=None):
    return _snapshot_facade().assistant_guidance_history(
        rows,
        min_confidence=min_confidence,
        scoring_policy=scoring_policy,
        outcomes_by_guidance=outcomes_by_guidance,
    )


def assistant_context_snapshot(*, limit=5000, top_n=10, include_prompt=True, include_sensitive=False):
    return _snapshot_facade().assistant_context_snapshot(
        limit=limit,
        top_n=top_n,
        include_prompt=include_prompt,
        include_sensitive=include_sensitive,
    )


def assistant_request_snapshot(*, limit=5000, top_n=10, include_prompt=True, include_offline_draft=True, include_sensitive=False):
    return _snapshot_facade().assistant_request_snapshot(
        limit=limit,
        top_n=top_n,
        include_prompt=include_prompt,
        include_offline_draft=include_offline_draft,
        include_sensitive=include_sensitive,
    )


def assistant_response_parse_payload(payload):
    return _snapshot_facade().assistant_response_parse_payload(payload)


def assistant_response_guidance_payload(payload):
    return _snapshot_facade().assistant_response_guidance_payload(payload)


def anti_overfit_snapshot(candidate_id=""):
    return _snapshot_facade().anti_overfit_snapshot(candidate_id)


def rolling_validation_snapshot(candidate_id="", windows=4):
    return _snapshot_facade().rolling_validation_snapshot(candidate_id, windows)


def assistant_cross_review_payload(payload):
    return _snapshot_facade().assistant_cross_review_payload(payload)


def save_assistant_guidance_payload(payload):
    return _snapshot_facade().save_assistant_guidance_payload(payload)


def latest_result_snapshot():
    return _runtime_facade().latest_result_snapshot(_app_context())


def latest_run_history_path():
    return _runtime_facade().latest_run_history_path(_app_context())


def user_profile_snapshot():
    return _runtime_facade().user_profile_snapshot(_app_context())


def load_presets():
    return _runtime_facade().load_presets(_app_context())


def match_preset_id(settings):
    return _runtime_facade().match_preset_id(_app_context(), settings)


def latest_cached_user_alphas(limit=None):
    web = _web()
    return web._latest_cached_user_alphas_service(limit=limit, load_config=web._load_run_config_provider())


def latest_cached_user_alpha_path():
    web = _web()
    return web._latest_cached_user_alpha_path_service(load_config=web._load_run_config_provider())


def cached_user_alpha_paths():
    web = _web()
    return web._cached_user_alpha_paths_service(load_config=web._load_run_config_provider())


def official_context_file_counts():
    web = _web()
    return web._official_context_file_counts_service(
        load_config=web._load_run_config_provider(),
        runtime_root=web._runtime_project_root_provider(),
        safe_error_message=web.safe_error_message,
    )


def read_official_context_metadata(filename):
    web = _web()
    return web._read_official_context_metadata_service(
        filename,
        load_config=web._load_run_config_provider(),
        runtime_root=web._runtime_project_root_provider(),
        safe_error_message=web.safe_error_message,
    )


def read_official_context_json(filename):
    web = _web()
    return web._read_official_context_json_service(
        filename,
        load_config=web._load_run_config_provider(),
        runtime_root=web._runtime_project_root_provider(),
        safe_error_message=web.safe_error_message,
    )


def cloud_alpha_summary(rows):
    web = _web()
    return web._cloud_alpha_summary_service(
        rows,
        load_config=web._load_run_config_provider(),
        runtime_root=web._runtime_project_root_provider(),
        safe_error_message=web.safe_error_message,
    )


def storage_jsonl_path(filename):
    return _runtime_facade().storage_jsonl_path(_app_context(), filename)


def read_storage_jsonl(filename, limit=500):
    return _runtime_facade().read_storage_jsonl(_app_context(), filename, limit=limit)


def read_storage_jsonl_stats(filename, limit=500):
    return _runtime_facade().read_storage_jsonl_stats(_app_context(), filename, limit=limit)


def public_run_config():
    return _runtime_facade().public_run_config(_app_context())
