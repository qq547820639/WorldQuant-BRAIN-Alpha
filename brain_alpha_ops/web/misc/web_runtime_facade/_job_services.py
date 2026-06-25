"""Job dispatch, candidate generation, and scoring service delegates."""
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
