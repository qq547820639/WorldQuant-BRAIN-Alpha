"""Job dispatch, snapshot factories, and submission/check delegates.

Consolidated from the former ``web_runtime_facade/`` subpackage
(``_job_services`` + ``_snapshots`` + ``_submission`` modules). These helpers
are bound to the public ``brain_alpha_ops.web`` facade at runtime and delegate
to service-layer functions via ``web.*`` attributes.
"""

from __future__ import annotations


def run_job(web, job_id: str, payload: dict):
    if payload.get("guided"):
        web.run_guided_job_service(
            job_id,
            payload,
            job_store=web.JOBS,
            run_config_from_payload=web.run_config_from_payload,
            compute_run_stats=web._compute_run_stats,
            safe_error_message=web.safe_error_message,
            log=web.logger,
        )
        return
    web.run_job_service(
        job_id,
        payload,
        job_store=web.JOBS,
        run_config_from_payload=web.run_config_from_payload,
        run_pipeline_from_config=web.run_pipeline_from_config,
        compute_run_stats=web._compute_run_stats,
        safe_error_message=web.safe_error_message,
        log=web.logger,
    )


def generate_candidates_payload(web, payload: dict) -> dict:
    return web._generate_candidates_payload(payload, run_config_from_payload=web.run_config_from_payload)


def lookup_sse_job(web, job_id: str) -> dict | None:
    for store in (web.JOBS, web.SYNC_JOBS, web.CHECK_JOBS, web.ASYNC_JOBS):
        row = store.get(job_id)
        if row:
            return row
    return None


def run_generate_candidates_job(web, job_id: str, payload: dict):
    def worker(body: dict) -> dict:
        result = web.generate_candidates_payload(body)
        if not result.get("ok"):
            return result
        try:
            from brain_alpha_ops.models import Candidate
            from brain_alpha_ops.research.repository import ResearchRepository

            run_config = web.run_config_from_payload(body)
            persistence = web._persist_generated_candidates(
                job_id,
                run_config,
                result,
                Candidate,
                ResearchRepository,
            )
        except Exception as exc:
            persistence = {
                "schema_version": "candidate-persistence-v1",
                "target": "candidates.jsonl",
                "persisted_count": 0,
                "error_count": 1,
                "errors": [web.safe_error_message(exc)],
            }
        summary = result.setdefault("summary", {})
        if isinstance(summary, dict):
            summary["persistence"] = persistence
        return result

    return web.run_simple_async_job_service(
        job_id,
        payload,
        store=web.ASYNC_JOBS,
        operation="generate_candidates",
        start_phase="candidate_generation",
        start_message="Generating candidate alphas.",
        worker=worker,
        safe_error_message=web.safe_error_message,
        error_payload=web.error_payload,
    )


def run_scoring_evaluate_job(web, job_id: str, payload: dict):
    from brain_alpha_ops.web_redline_scoring import handle_scoring_evaluate

    return web.run_simple_async_job_service(
        job_id,
        payload,
        store=web.ASYNC_JOBS,
        operation="scoring_evaluate",
        start_phase="scoring",
        start_message="Scoring candidate through the official scoring pipeline.",
        worker=handle_scoring_evaluate,
        safe_error_message=web.safe_error_message,
        error_payload=web.error_payload,
    )


def lifecycle_from_job(web, job: dict) -> list[dict]:
    return web._lifecycle_from_job_service(job, read_storage_jsonl=web._read_storage_jsonl, limit=None)


def alpha_lifecycle_history(web, **kwargs) -> dict:
    from brain_alpha_ops.web_alpha_lifecycle import alpha_lifecycle_history_payload

    return alpha_lifecycle_history_payload(read_storage_jsonl=web._read_storage_jsonl, **kwargs)


def cloud_alpha_snapshot(web, limit: int | None = None) -> dict:
    return web._cloud_alpha_snapshot_service(
        limit=limit,
        load_config=web.load_run_config,
        runtime_root=web.runtime_project_root,
        safe_error_message=web.safe_error_message,
        stale_seconds=web.CLOUD_SYNC_STALE_SECONDS,
    )


def cloud_alpha_cache_probe(web) -> dict:
    return web._cloud_alpha_cache_probe_service(
        load_config=web.load_run_config,
        stale_seconds=web.CLOUD_SYNC_STALE_SECONDS,
    )


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


def refresh_cloud_context_for_check(
    web,
    api,
    repo,
    sync_range: str,
    job_id: str,
    total: int,
    mode: str,
    region: str = "",
    *,
    refresh_remote: bool = False,
):
    return web.refresh_cloud_context_for_check_service(
        api,
        repo,
        sync_range,
        job_id,
        total,
        mode,
        region,
        refresh_remote=refresh_remote,
        store=web.CHECK_JOBS,
        official_context_file_counts=web._official_context_file_counts,
        datasets_from_fields=web._datasets_from_fields,
        persist_official_context=web._persist_official_context,
        safe_error_message=web.safe_error_message,
    )


def datasets_from_fields(web, fields: list[dict]) -> list[dict]:
    return web._datasets_from_fields_service(
        fields,
        load_config=web.load_run_config,
        runtime_root=web.runtime_project_root,
        safe_error_message=web.safe_error_message,
    )


def persist_official_context(web, fields: list[dict], operators: list[dict], datasets: list[dict]) -> None:
    web._persist_official_context_service(
        fields,
        operators,
        datasets,
        load_config=web.load_run_config,
        runtime_root=web.runtime_project_root,
        safe_error_message=web.safe_error_message,
    )


def save_official_context_json(web, filename: str, items: list[dict]) -> None:
    web._save_official_context_json_service(
        filename,
        items,
        load_config=web.load_run_config,
        runtime_root=web.runtime_project_root,
    )


def passed_candidates_from_payload(web, payload: dict) -> list[dict]:
    return web._passed_candidates_from_payload(payload, web.JOBS)


def check_candidate_availability(
    web,
    candidate: dict,
    mode: str,
    api,
    ledger,
    cloud_alphas: list[dict],
    cloud_error: str = "",
    observability_preflight: dict | None = None,
) -> dict:
    return web._check_candidate_availability(
        candidate,
        mode,
        api,
        ledger,
        cloud_alphas,
        cloud_error,
        observability_preflight,
        safe_error_message=web.safe_error_message,
        observability_submission_preflight=web.observability_submission_preflight,
    )


def check_candidate(web, payload: dict) -> dict:
    return web.check_candidate_payload(
        payload,
        candidate_from_payload=web.candidate_from_payload,
        run_config_from_payload=web.run_config_from_payload,
        api_from_run_config=web.api_from_run_config,
        repository_factory=web.ResearchRepository,
        ledger_factory=web.SubmissionLedger,
        refresh_cloud_context_for_check=web.refresh_cloud_context_for_check,
        payload_truthy=web.payload_truthy,
        check_candidate_availability=web.check_candidate_availability,
        observability_submission_preflight=web.observability_submission_preflight,
        web_error=web._web_error,
    )


def submission_preflight_error(web, candidate: dict, run_config) -> str:
    return web._submission_preflight_error_message(
        candidate,
        run_config,
        ledger_factory=web.SubmissionLedger,
        cloud_alpha_snapshot=web.cloud_alpha_snapshot,
        cloud_status_for=web.cloud_status_for,
    )


def submission_preflight_advisory(web, candidate: dict, run_config) -> dict:
    return web._submission_preflight_advisory(
        candidate,
        run_config,
        ledger_factory=web.SubmissionLedger,
        cloud_alpha_snapshot=web.cloud_alpha_snapshot,
        cloud_status_for=web.cloud_status_for,
    )


def observability_submission_preflight(web, storage_dir: str, *, limit: int = 5000, top_n: int = 5) -> dict:
    return web._observability_submission_preflight(
        storage_dir,
        limit=limit,
        top_n=top_n,
        observability_builder=web.build_research_observability_snapshot,
        safe_error_message=web.safe_error_message,
    )


def record_submit_blocked(web, payload: dict, candidate: dict, run_config, failure_reason: str) -> None:
    web._record_submit_blocked_event(
        payload,
        candidate,
        run_config,
        failure_reason,
        repository_factory=web.ResearchRepository,
        log=web.logger,
    )


def submit_candidate(web, payload: dict) -> dict:
    return web.submit_candidate_payload(
        payload,
        candidate_from_payload=web.candidate_from_payload,
        run_config_from_payload=web.run_config_from_payload,
        submission_preflight_advisory=web.submission_preflight_advisory,
        record_submit_blocked=web.record_submit_blocked,
        official_alpha_id=web.official_alpha_id,
        observability_submission_preflight=web.observability_submission_preflight,
        payload_truthy=web.payload_truthy,
        api_from_run_config=web.api_from_run_config,
        submit_readiness_hard_gate=web.live_submit_readiness_hard_gate,
    )


def load_check_results(web) -> dict:
    return web._load_check_results_service(
        read_storage_jsonl=web._read_storage_jsonl,
        safe_error_message=web.safe_error_message,
        log=web.logger,
        limit=None,
    )


def submit_batch(web, payload: dict) -> dict:
    return web.submit_batch_payload(
        payload,
        run_config_from_payload=web.run_config_from_payload,
        observability_submission_preflight=web.observability_submission_preflight,
        submit_candidate=web.submit_candidate,
        candidate_from_payload=web.candidate_from_payload,
        web_error=web._web_error,
        payload_truthy=web.payload_truthy,
        submission_preflight_advisory=web.submission_preflight_advisory,
        submit_readiness_hard_gate=web.live_submit_readiness_hard_gate,
    )


def run_submit_batch_job(web, job_id: str, payload: dict):
    import time

    started_at = time.time()

    def _progress(progress: dict) -> None:
        progress = dict(progress or {})
        message = str(progress.get("message") or "Submitting batch.")
        done = int(progress.get("done", progress.get("submitted", 0)) or 0)
        total = int(progress.get("total", 0) or 0)
        web.progress_update(
            web.ASYNC_JOBS,
            job_id,
            started_at,
            operation="submit_batch",
            phase=str(progress.get("phase") or "submitting"),
            message=message,
            done=done,
            total=total,
            submitted=int(progress.get("submitted", 0) or 0),
            failed=int(progress.get("failed", 0) or 0),
            current_alpha_id=str(progress.get("current_alpha_id") or ""),
        )

    def _worker(body: dict) -> dict:
        if not web.SUBMIT_LOCK.acquire(blocking=False):
            return {"ok": False, "error_code": "CONFLICT_RUNNING", "error": "已有提交任务正在运行，请完成后再操作。"}
        try:
            return web.submit_batch_payload(
                body,
                run_config_from_payload=web.run_config_from_payload,
                observability_submission_preflight=web.observability_submission_preflight,
                submit_candidate=web.submit_candidate,
                candidate_from_payload=web.candidate_from_payload,
                web_error=web._web_error,
                payload_truthy=web.payload_truthy,
                progress_callback=_progress,
            )
        finally:
            web.SUBMIT_LOCK.release()

    return web.run_simple_async_job_service(
        job_id,
        payload,
        store=web.ASYNC_JOBS,
        operation="submit_batch",
        start_phase="submitting",
        start_message="Preparing batch submission.",
        worker=_worker,
        safe_error_message=web.safe_error_message,
        error_payload=web.error_payload,
    )


def storage_jsonl_path(web, filename: str):
    return web._storage_jsonl_path_service(filename, load_config=web.load_run_config)


def read_storage_jsonl(web, filename: str, *, limit: int | None = 500) -> list[dict]:
    return web._read_storage_jsonl_service(filename, limit=limit, load_config=web.load_run_config)


def read_storage_jsonl_stats(web, filename: str, *, limit: int = 500) -> dict:
    return web._read_storage_jsonl_stats_service(filename, limit=limit, load_config=web.load_run_config)


def public_run_config(web) -> dict:
    from brain_alpha_ops.web_config import managed_credentials_available

    config = web.load_run_config().to_dict()
    credentials = config.get("credentials", {})
    config["credentials"] = {
        "username": "",
        "password": "",
        "token": "",
        "username_env": credentials.get("username_env", "BRAIN_USERNAME"),
        "password_env": credentials.get("password_env", "BRAIN_PASSWORD"),
        "token_env": credentials.get("token_env", "BRAIN_TOKEN"),
        "managed_credentials_available": managed_credentials_available(credentials),
    }
    return config


def find_free_port(web, start: int, host: str) -> int:
    return web._find_free_port_service(start, host=host)


__all__ = [
    "alpha_lifecycle_history",
    "candidate_from_payload",
    "check_candidate",
    "check_candidate_availability",
    "cloud_alpha_cache_probe",
    "cloud_alpha_snapshot",
    "datasets_from_fields",
    "find_free_port",
    "generate_candidates_payload",
    "latest_result_snapshot",
    "latest_run_history_path",
    "lifecycle_from_job",
    "load_check_results",
    "load_presets",
    "lookup_sse_job",
    "match_preset_id",
    "maybe_archive_lifecycle",
    "observability_submission_preflight",
    "passed_candidates_from_payload",
    "persist_official_context",
    "public_run_config",
    "read_storage_jsonl",
    "read_storage_jsonl_stats",
    "refresh_cloud_context_for_check",
    "run_check_batch_job",
    "run_generate_candidates_job",
    "run_job",
    "run_scoring_evaluate_job",
    "run_submit_batch_job",
    "run_sync_job",
    "save_official_context_json",
    "snapshot_facade",
    "snapshot_runtime",
    "storage_jsonl_path",
    "submit_batch",
    "submit_candidate",
    "submission_preflight_advisory",
    "submission_preflight_error",
    "sync_cloud_alphas",
    "user_profile_snapshot",
]
