"""Official context, candidate checking, submission, and storage delegates."""
from __future__ import annotations


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
