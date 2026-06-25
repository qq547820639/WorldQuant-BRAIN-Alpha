"""Dispatch context builder and connection helpers."""
from __future__ import annotations

from brain_alpha_ops.brain_api.base import BrainAPIError

from ._logging import logger


def handler_dispatch_context(web):
    return web.WebHandlerDispatchContext(
        core=web.WebDispatchCoreContext(
            route_for=web.route_for,
            web_error=web._web_error,
            payload_truthy=web.payload_truthy,
            bounded_query_int=web._bounded_query_int,
            bounded_query_float=web._bounded_query_float,
            rate_limit_request=web.rate_limit_request,
            safe_error_message=web.safe_error_message,
            error_payload=web.error_payload,
        ),
        session=web.WebDispatchSessionContext(
            remote_admin_required=web._remote_admin_required,
            has_valid_admin_token=web._has_valid_admin_token,
            get_or_create_session=web._get_or_create_session,
            stream_token_for_session=web._stream_token_for_session,
            session_cookie_header=web._session_cookie_header,
            session_status=web._session_status,
            mark_brain_connection_verified=web._mark_brain_connection_verified,
            clear_brain_connection_verified=web._clear_brain_connection_verified,
            payload_with_brain_session_credentials=web._payload_with_brain_session_credentials,
            render_html=web._render_html,
            session_end_payload=web.session_end_payload,
            expire_session=web._expire_session,
            expired_session_cookie_header=web._expired_session_cookie_header,
            start_shutdown=lambda: web._start_thread(web.shutdown_server),
        ),
        job=web.WebDispatchJobContext(
            job_status_payload=web.job_status_payload,
            active_job_payload=web.active_job_payload,
            lifecycle_payload=web.lifecycle_payload,
            jobs=web.JOBS,
            sync_jobs=web.SYNC_JOBS,
            check_jobs=web.CHECK_JOBS,
            async_jobs=web.ASYNC_JOBS,
            enrich_progress=web._enrich_progress,
            background_job_start_payload=web.background_job_start_payload,
            start_run_job=lambda job_id, body: web._submit_background_job(web.run_job, job_id, body),
            stop_job_payload=web.stop_job_payload,
            active_auxiliary_operation=web.active_auxiliary_operation,
            run_simple_async_job_service=web.run_simple_async_job_service,
        ),
        config=web.WebDispatchConfigContext(
            health_payload=web.health_payload,
            profile_payload=web.profile_payload,
            presets_payload=web.presets_payload,
            public_run_config=web.public_run_config,
            public_config_schema=web.public_config_schema,
            save_run_config_payload=web.save_run_config_payload,
            connection_test_post_payload=web.connection_test_post_payload,
            test_connection=web.test_connection,
            validate_run_payload=lambda body: web.run_config_from_payload(body),
            load_presets=web._load_presets,
            run_config_from_payload=web.run_config_from_payload,
        ),
        research=web.WebDispatchResearchContext(
            latest_result_snapshot=web.latest_result_snapshot,
            lifecycle_from_job=web.lifecycle_from_job,
            alpha_lifecycle_history=web.alpha_lifecycle_history,
            cloud_alpha_snapshot=web.cloud_alpha_snapshot,
            official_context_file_counts=web._official_context_file_counts,
            research_memory_snapshot=web.research_memory_snapshot,
            research_knowledge_snapshot=web.research_knowledge_snapshot,
            research_observability_snapshot=web.research_observability_snapshot,
            prompt_run_ledger_snapshot=web.prompt_run_ledger_snapshot,
            sqlite_index_snapshot=web.sqlite_index_snapshot,
            sqlite_expression_lookup_payload=web.sqlite_expression_lookup_payload,
            sqlite_record_lookup_payload=web.sqlite_record_lookup_payload,
            load_check_results=web.load_check_results,
            user_profile_snapshot=web._user_profile_snapshot,
            cloud_alpha_cache_probe=web.cloud_alpha_cache_probe,
        ),
        assistant=web.WebDispatchAssistantContext(
            assistant_context_snapshot=web.assistant_context_snapshot,
            assistant_guidance_snapshot=web.assistant_guidance_snapshot,
            assistant_request_snapshot=web.assistant_request_snapshot,
            anti_overfit_snapshot=web.anti_overfit_snapshot,
            rolling_validation_snapshot=web.rolling_validation_snapshot,
            assistant_response_parse_post_payload=web.assistant_response_parse_post_payload,
            assistant_response_parse_payload=web.assistant_response_parse_payload,
            assistant_response_guidance_post_payload=web.assistant_response_guidance_post_payload,
            assistant_response_guidance_payload=web.assistant_response_guidance_payload,
            assistant_cross_review_payload=web.assistant_cross_review_payload,
            save_assistant_guidance_post_payload=web.save_assistant_guidance_post_payload,
            save_assistant_guidance_payload=web.save_assistant_guidance_payload,
        ),
        actions=web.WebDispatchActionContext(
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
        ),
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
            profile = api.get_user_profile()
            if isinstance(profile, dict) and profile.get("error"):
                raise BrainAPIError(
                    str(profile.get("error") or "BRAIN profile check failed"),
                    status_code=_profile_status_code(profile),
                    payload=profile,
                )
        auth_mode = ""
        if isinstance(auth_result, dict):
            auth_mode = str(auth_result.get("auth") or auth_result.get("environment") or "")
        return {"ok": True, "environment": str(run_config.environment), "auth": auth_mode}
    except Exception as exc:
        logger.error("web connection test failed")
        return web._web_error(exc, "CONNECTION_FAILED")


def _profile_status_code(profile: dict) -> int | None:
    try:
        status_code = int(profile.get("status_code") or 0)
    except (TypeError, ValueError):
        return None
    return status_code if status_code > 0 else None
