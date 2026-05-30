"""Runtime-bound helpers for the public ``brain_alpha_ops.web`` facade."""

from __future__ import annotations

import json
import os
import sys


def handler_dispatch_context(web):
    return web.WebHandlerDispatchContext(
        route_for=web.route_for,
        web_error=web._web_error,
        payload_truthy=web.payload_truthy,
        bounded_query_int=web._bounded_query_int,
        bounded_query_float=web._bounded_query_float,
        remote_admin_required=web._remote_admin_required,
        has_valid_admin_token=web._has_valid_admin_token,
        get_or_create_session=web._get_or_create_session,
        stream_token_for_session=web._stream_token_for_session,
        session_cookie_header=web._session_cookie_header,
        render_html=web._render_html,
        job_status_payload=web.job_status_payload,
        active_job_payload=web.active_job_payload,
        lifecycle_payload=web.lifecycle_payload,
        health_payload=web.health_payload,
        profile_payload=web.profile_payload,
        presets_payload=web.presets_payload,
        jobs=web.JOBS,
        sync_jobs=web.SYNC_JOBS,
        check_jobs=web.CHECK_JOBS,
        async_jobs=web.ASYNC_JOBS,
        enrich_progress=web._enrich_progress,
        public_run_config=web.public_run_config,
        public_config_schema=web.public_config_schema,
        save_run_config_payload=web.save_run_config_payload,
        rate_limit_request=web.rate_limit_request,
        latest_result_snapshot=web.latest_result_snapshot,
        lifecycle_from_job=web.lifecycle_from_job,
        cloud_alpha_snapshot=web.cloud_alpha_snapshot,
        research_memory_snapshot=web.research_memory_snapshot,
        research_knowledge_snapshot=web.research_knowledge_snapshot,
        research_observability_snapshot=web.research_observability_snapshot,
        prompt_run_ledger_snapshot=web.prompt_run_ledger_snapshot,
        sqlite_index_snapshot=web.sqlite_index_snapshot,
        sqlite_expression_lookup_payload=web.sqlite_expression_lookup_payload,
        sqlite_record_lookup_payload=web.sqlite_record_lookup_payload,
        assistant_context_snapshot=web.assistant_context_snapshot,
        assistant_guidance_snapshot=web.assistant_guidance_snapshot,
        assistant_request_snapshot=web.assistant_request_snapshot,
        anti_overfit_snapshot=web.anti_overfit_snapshot,
        rolling_validation_snapshot=web.rolling_validation_snapshot,
        load_check_results=web.load_check_results,
        user_profile_snapshot=web._user_profile_snapshot,
        load_presets=web._load_presets,
        connection_test_post_payload=web.connection_test_post_payload,
        test_connection=web.test_connection,
        validate_run_payload=lambda body: web.run_config_from_payload(body),
        background_job_start_payload=web.background_job_start_payload,
        start_run_job=lambda job_id, body: web._submit_background_job(web.run_job, job_id, body),
        stop_job_payload=web.stop_job_payload,
        active_auxiliary_operation=web.active_auxiliary_operation,
        start_sync_job=lambda job_id, body: web._submit_background_job(web.run_sync_job, job_id, body),
        check_candidate=web.check_candidate,
        generate_candidates_payload=web.generate_candidates_payload,
        start_generate_candidates_job=lambda job_id, body: web._submit_background_job(web.run_generate_candidates_job, job_id, body),
        start_check_batch_job=lambda job_id, body: web._submit_background_job(web.run_check_batch_job, job_id, body),
        start_scoring_evaluate_job=lambda job_id, body: web._submit_background_job(web.run_scoring_evaluate_job, job_id, body),
        start_submit_batch_job=lambda job_id, body: web._submit_background_job(web.run_submit_batch_job, job_id, body),
        submit_lock=web.SUBMIT_LOCK,
        submit_candidate=web.submit_candidate,
        submit_batch=web.submit_batch,
        assistant_response_parse_post_payload=web.assistant_response_parse_post_payload,
        assistant_response_parse_payload=web.assistant_response_parse_payload,
        assistant_response_guidance_post_payload=web.assistant_response_guidance_post_payload,
        assistant_response_guidance_payload=web.assistant_response_guidance_payload,
        assistant_cross_review_payload=web.assistant_cross_review_payload,
        save_assistant_guidance_post_payload=web.save_assistant_guidance_post_payload,
        save_assistant_guidance_payload=web.save_assistant_guidance_payload,
        session_end_payload=web.session_end_payload,
        expire_session=web._expire_session,
        expired_session_cookie_header=web._expired_session_cookie_header,
        start_shutdown=lambda: web._start_thread(web.shutdown_server),
    )


def cloud_status_for(web, candidate: dict, cloud_alphas: list[dict]) -> dict:
    return web._cloud_status_for(candidate, cloud_alphas)


def cloud_similarity_risk(web, candidate: dict, cloud_alphas: list[dict]) -> dict:
    return web._cloud_similarity_risk(candidate, cloud_alphas)


def test_connection(web, payload: dict) -> dict:
    try:
        run_config = web.run_config_from_payload(payload)
        api = web.api_from_run_config(run_config)
        auth_result = api.authenticate()
        if str(run_config.environment).lower() == "production" and hasattr(api, "get_user_profile"):
            api.get_user_profile()
        auth_mode = ""
        if isinstance(auth_result, dict):
            auth_mode = str(auth_result.get("auth") or auth_result.get("environment") or "")
        return {"ok": True, "environment": str(run_config.environment), "auth": auth_mode}
    except Exception as exc:
        return web._web_error(exc, "CONNECTION_FAILED")


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
    return web.run_simple_async_job_service(
        job_id,
        payload,
        store=web.ASYNC_JOBS,
        operation="generate_candidates",
        start_phase="candidate_generation",
        start_message="Generating candidate alphas.",
        worker=web.generate_candidates_payload,
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
    return web._lifecycle_from_job_service(job, read_storage_jsonl=web._read_storage_jsonl, limit=1000)


def cloud_alpha_snapshot(web, limit: int | None = None) -> dict:
    return web._cloud_alpha_snapshot_service(
        limit=limit,
        load_config=web.load_run_config,
        runtime_root=web.runtime_project_root,
        safe_error_message=web.safe_error_message,
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
    )


def load_check_results(web) -> dict:
    return web._load_check_results_service(
        read_storage_jsonl=web._read_storage_jsonl,
        safe_error_message=web.safe_error_message,
        log=web.logger,
        limit=5000,
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


def read_storage_jsonl(web, filename: str, *, limit: int = 500) -> list[dict]:
    return web._read_storage_jsonl_service(filename, limit=limit, load_config=web.load_run_config)


def read_storage_jsonl_stats(web, filename: str, *, limit: int = 500) -> dict:
    return web._read_storage_jsonl_stats_service(filename, limit=limit, load_config=web.load_run_config)


def public_run_config(web) -> dict:
    config = web.load_run_config().to_dict()
    credentials = config.get("credentials", {})
    config["credentials"] = {
        "username": "",
        "password": "",
        "token": "",
        "username_env": credentials.get("username_env", "BRAIN_USERNAME"),
        "password_env": credentials.get("password_env", "BRAIN_PASSWORD"),
        "token_env": credentials.get("token_env", "BRAIN_TOKEN"),
    }
    return config


def find_free_port(web, start: int, host: str) -> int:
    return web._find_free_port_service(start, host=host)


def shutdown_server(web):
    web._shutdown_server_service(web.SERVER, web.SERVER_STOP)


def serve(
    web,
    port: int | None = None,
    open_browser: bool = True,
    host: str | None = None,
    session_ttl_seconds: int | None = None,
    allow_multiple_sessions: bool | None = None,
    allow_remote: bool = False,
    secure_cookies: bool | None = None,
) -> str:
    host = web.HOST if host is None else host
    run_config = web.load_run_config()
    web.web_session.set_remote_policy(
        allow_remote=allow_remote,
        admin_token_env=str(getattr(run_config.web, "admin_token_env", web.web_session.DEFAULT_ADMIN_TOKEN_ENV)),
    )
    web.web_session.require_remote_admin_token()
    web.configure_session_policy(
        session_ttl_seconds,
        allow_multiple_sessions,
        secure_cookies=bool(allow_remote) if secure_cookies is None else secure_cookies,
    )
    url, server = web._serve_service(
        port=port,
        open_browser=open_browser,
        host=host,
        default_port=web.DEFAULT_PORT,
        handler_class=web.Handler,
        stop_event=web.SERVER_STOP,
        configure_session_policy=web.configure_session_policy,
        normalize_host=web.normalize_host,
        loopback_bind_hosts=web.LOOPBACK_BIND_HOSTS,
        allow_remote=allow_remote,
        session_ttl_seconds=session_ttl_seconds,
        allow_multiple_sessions=allow_multiple_sessions,
        secure_cookies=web.web_session.SESSION_MANAGER.secure_cookies,
    )
    web.SERVER = server
    return url


def smoke_test_server(web, port: int | None = None) -> dict:
    return web._smoke_test_server_service(
        port=port,
        default_port=web.DEFAULT_PORT,
        serve_func=web.serve,
        shutdown_func=web.shutdown_server,
        parse_cookies=web._parse_cookies,
        cookie_name=web.SESSION_COOKIE_NAME,
        csrf_for_session=web._csrf_for_session,
    )


def main(web, argv: list[str] | None = None) -> int:
    import argparse

    def safe_print(message: str) -> None:
        stream = getattr(sys, "stdout", None)
        if stream is None:
            return
        try:
            print(message)
        except Exception:
            return

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--frontend", choices=("inline", "react"), default="")
    args = parser.parse_args(argv)
    if args.frontend:
        env_name = getattr(getattr(web, "web_html", None), "WEB_FRONTEND_ENV", "BRAIN_ALPHA_OPS_WEB_FRONTEND")
        os.environ[env_name] = args.frontend
        reset_cache = getattr(getattr(web, "web_html", None), "reset_html_cache", None)
        if callable(reset_cache):
            reset_cache()
    run_config = web.load_run_config(args.config or None)
    if args.smoke_test:
        web.config_from_payload({"environment": "production"})
        result = web.smoke_test_server(port=args.port or run_config.web.port)
        safe_print(json.dumps({"ok": True, "status": "web ready", **result}, ensure_ascii=False))
        return 0
    url = web.serve(
        port=args.port or run_config.web.port,
        open_browser=run_config.web.open_browser and not args.no_browser,
        host=run_config.web.host,
        session_ttl_seconds=run_config.web.session_ttl_seconds,
        allow_multiple_sessions=run_config.web.allow_multiple_sessions,
        allow_remote=run_config.web.allow_remote,
        secure_cookies=run_config.web.secure_cookies or run_config.web.allow_remote,
    )
    safe_print("BRAIN Alpha Ops 已启动")
    safe_print(f"访问地址：{url}")
    safe_print("关闭此窗口或按 Ctrl+C 可停止本地服务。")
    try:
        while not web.SERVER_STOP.wait(3600):
            pass
    except KeyboardInterrupt:
        web.shutdown_server()
    return 0
