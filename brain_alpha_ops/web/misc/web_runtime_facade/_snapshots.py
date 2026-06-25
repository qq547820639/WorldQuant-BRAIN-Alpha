"""Snapshot factories, preset/candidate helpers, and sync/check job delegates."""
from __future__ import annotations


def snapshot_runtime(web):
    return web.WebSnapshotRuntime(
        load_config=web.load_run_config,
        web_error=web._web_error,
        bounded_query_float=web._bounded_query_float,
        payload_truthy=web.payload_truthy,
        read_storage_jsonl=web._read_storage_jsonl,
        run_config_from_payload=web.run_config_from_payload,
        cloud_alpha_snapshot=web.cloud_alpha_snapshot,
        storage_jsonl_path=web._storage_jsonl_path,
        safe_error_message=web.safe_error_message,
        job_store=web.JOBS,
        sync_job_store=web.SYNC_JOBS,
        check_job_store=web.CHECK_JOBS,
        enrich_progress=web._enrich_progress,
        observability_builder=web.build_research_observability_snapshot,
    )


def snapshot_facade(web):
    return web.WebSnapshotFacade(
        runtime_factory=web._snapshot_runtime,
        latest_result_snapshot_func=web.latest_result_snapshot,
        assistant_context_snapshot_func=web.assistant_context_snapshot,
        assistant_guidance_snapshot_func=web.assistant_guidance_snapshot,
    )


def latest_result_snapshot(web) -> dict:
    return web.WebSnapshotFacade(
        runtime_factory=web._snapshot_runtime,
        latest_run_history_path_func=web._latest_run_history_path,
    ).latest_result_snapshot()


def latest_run_history_path(web):
    return web._snapshot_facade().latest_run_history_path()


def user_profile_snapshot(web) -> dict:
    return web._snapshot_facade().user_profile_snapshot()


def load_presets(web) -> dict:
    return web._load_presets_service(runtime_root=web.runtime_project_root, log=web.logger)


def match_preset_id(web, settings: dict) -> str:
    return web._match_preset_id_service(settings, web._load_presets())


def candidate_from_payload(web, payload: dict) -> dict:
    return web._candidate_from_payload(payload, web.JOBS)


def sync_cloud_alphas(web, payload: dict) -> dict:
    return web.sync_cloud_alphas_payload(
        payload,
        run_config_from_payload=web.run_config_from_payload,
        api_from_run_config=web.api_from_run_config,
        repository_factory=web.ResearchRepository,
        datasets_from_fields=web._datasets_from_fields,
        persist_official_context=web._persist_official_context,
        default_fields=list(web.DEFAULT_FIELDS),
        default_operators=list(web.DEFAULT_OPERATORS),
    )


def run_sync_job(web, job_id: str, payload: dict):
    return web.run_sync_job_service(
        job_id,
        payload,
        store=web.SYNC_JOBS,
        run_config_from_payload=web.run_config_from_payload,
        api_from_run_config=web.api_from_run_config,
        repository_factory=web.ResearchRepository,
        datasets_from_fields=web._datasets_from_fields,
        persist_official_context=web._persist_official_context,
        default_fields=list(web.DEFAULT_FIELDS),
        default_operators=list(web.DEFAULT_OPERATORS),
        safe_error_message=web.safe_error_message,
        error_payload=web.error_payload,
    )


def run_check_batch_job(web, job_id: str, payload: dict):
    return web.run_check_batch_job_service(
        job_id,
        payload,
        store=web.CHECK_JOBS,
        passed_candidates_from_payload=web.passed_candidates_from_payload,
        run_config_from_payload=web.run_config_from_payload,
        api_from_run_config=web.api_from_run_config,
        repository_factory=web.ResearchRepository,
        ledger_factory=web.SubmissionLedger,
        refresh_cloud_context_for_check=web.refresh_cloud_context_for_check,
        payload_truthy=web.payload_truthy,
        check_candidate_availability=web.check_candidate_availability,
        observability_submission_preflight=web.observability_submission_preflight,
        safe_error_message=web.safe_error_message,
        error_payload=web.error_payload,
    )


def maybe_archive_lifecycle(web) -> None:
    web._LAST_ARCHIVE_CHECK = web._maybe_archive_lifecycle_service(
        last_archive_check=web._LAST_ARCHIVE_CHECK,
        interval_seconds=web._ARCHIVE_CHECK_INTERVAL,
        load_config=web.load_run_config,
        repository_factory=web.ResearchRepository,
        safe_error_message=web.safe_error_message,
        log=web.logger,
    )
