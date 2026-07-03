"""Consolidated web facade bindings: helpers, candidate, config, job, session.

Combines the former ``_helpers.py``, ``_candidate.py``, ``_config.py``,
``_job.py``, and ``_session.py`` modules.
"""

from __future__ import annotations

from brain_alpha_ops.web_job_registry import resolve_web_job_registry


# ---------------------------------------------------------------------------
# Shared lazy-accessor helpers (formerly _helpers.py)
# ---------------------------------------------------------------------------


def _web():
    from brain_alpha_ops import web

    return web


def _app_context():
    return _web()._app_context()


def _runtime_facade():
    return _web()._runtime_facade


def _snapshot_facade():
    from brain_alpha_ops import web

    return web._snapshot_facade()


# ---------------------------------------------------------------------------
# Candidate / check / submit / preflight bindings (formerly _candidate.py)
# ---------------------------------------------------------------------------


def generate_candidates_payload(payload):
    return _runtime_facade().generate_candidates_payload(_app_context(), payload)


def run_generate_candidates_job(job_id, payload):
    return _runtime_facade().run_generate_candidates_job(_app_context(), job_id, payload)


def run_scoring_evaluate_job(job_id, payload):
    return _runtime_facade().run_scoring_evaluate_job(_app_context(), job_id, payload)


def run_submit_batch_job(job_id, payload):
    return _runtime_facade().run_submit_batch_job(_app_context(), job_id, payload)


def candidate_from_payload(payload):
    return _runtime_facade().candidate_from_payload(_app_context(), payload)


def sync_cloud_alphas(payload):
    return _runtime_facade().sync_cloud_alphas(_app_context(), payload)


def run_sync_job(job_id, payload):
    return _runtime_facade().run_sync_job(_app_context(), job_id, payload)


def run_check_batch_job(job_id, payload):
    return _runtime_facade().run_check_batch_job(_app_context(), job_id, payload)


def refresh_cloud_context_for_check(api, repo, sync_range, job_id, total, mode, region="", refresh_remote=False):
    return _runtime_facade().refresh_cloud_context_for_check(
        _app_context(),
        api,
        repo,
        sync_range,
        job_id,
        total,
        mode,
        region,
        refresh_remote=refresh_remote,
    )


def datasets_from_fields(fields):
    return _runtime_facade().datasets_from_fields(_app_context(), fields)


def persist_official_context(fields, operators, datasets):
    return _runtime_facade().persist_official_context(_app_context(), fields, operators, datasets)


def save_official_context_json(filename, items):
    return _runtime_facade().save_official_context_json(_app_context(), filename, items)


def passed_candidates_from_payload(payload):
    return _runtime_facade().passed_candidates_from_payload(_app_context(), payload)


def check_candidate_availability(candidate, mode, api, ledger, cloud_alphas, cloud_error="", observability_preflight=None):
    return _runtime_facade().check_candidate_availability(
        _app_context(),
        candidate,
        mode,
        api,
        ledger,
        cloud_alphas,
        cloud_error,
        observability_preflight,
    )


def cloud_status_for(candidate, cloud_alphas):
    return _runtime_facade().cloud_status_for(_app_context(), candidate, cloud_alphas)


def cloud_similarity_risk(candidate, cloud_alphas):
    return _runtime_facade().cloud_similarity_risk(_app_context(), candidate, cloud_alphas)


def check_candidate(payload):
    return _runtime_facade().check_candidate(_app_context(), payload)


def submission_preflight_error(candidate, run_config):
    return _runtime_facade().submission_preflight_error(_app_context(), candidate, run_config)


# P3-1: alias kept for backwards-compatibility with callers that imported
# the longer ``submission_preflight_error_message`` name from this module.
submission_preflight_error_message = submission_preflight_error


def submission_preflight_advisory(candidate, run_config):
    return _runtime_facade().submission_preflight_advisory(_app_context(), candidate, run_config)


def observability_submission_preflight(storage_dir, limit=5000, top_n=5):
    return _runtime_facade().observability_submission_preflight(_app_context(), storage_dir, limit=limit, top_n=top_n)


def record_submit_blocked(payload, candidate, run_config, failure_reason):
    return _runtime_facade().record_submit_blocked(_app_context(), payload, candidate, run_config, failure_reason)


def submit_candidate(payload):
    return _runtime_facade().submit_candidate(_app_context(), payload)


def load_check_results():
    return _runtime_facade().load_check_results(_app_context())


def submit_batch(payload):
    return _runtime_facade().submit_batch(_app_context(), payload)


# ---------------------------------------------------------------------------
# Run/config payload bindings (formerly _config.py)
# ---------------------------------------------------------------------------


def load_run_config_provider():
    web = _web()
    return web._load_run_config


def runtime_project_root_provider():
    web = _web()
    return web._runtime_project_root


def run_config_from_payload(payload):
    web = _web()
    return web._run_config_from_payload(payload, loader=web._load_run_config_provider())


def config_from_payload(payload):
    web = _web()
    return web._config_from_payload(payload, loader=web._load_run_config_provider())


def save_run_config_payload(payload):
    web = _web()
    return web._save_run_config_payload(payload, loader=web._load_run_config_provider())


# ---------------------------------------------------------------------------
# Job registry bindings (formerly _job.py)
# ---------------------------------------------------------------------------


def job_registry():
    return _web().JOB_REGISTRY


def job_registry_view():
    return resolve_web_job_registry(_app_context())


def active_auxiliary_operation(exclude="", allow_production=False):
    web = _web()
    registry = job_registry_view()
    return web._active_auxiliary_operation_service(
        production_store=registry.jobs,
        sync_store=registry.sync_jobs,
        check_store=registry.check_jobs,
        submit_lock=registry.submit_lock,
        exclude=exclude,
        allow_production=allow_production,
    )


def rate_limit_request(key, method, path):
    return job_registry_view().rate_limiter.check(key=key, method=method, path=path)


def submit_background_job(target, *args) -> None:
    job_registry_view().task_executor.submit(target, *args)


# ---------------------------------------------------------------------------
# Session policy bindings (formerly _session.py)
# ---------------------------------------------------------------------------


def configure_session_policy(
    ttl_seconds: int | float | None = None,
    allow_multiple_sessions: bool | None = None,
    secure_cookies: bool | None = None,
) -> None:
    web = _web()
    web.web_session.configure_session_policy(ttl_seconds, allow_multiple_sessions, secure_cookies)
    web.SESSION_TTL_SECONDS = web.web_session.session_ttl_seconds()
    web.SESSION_ALLOW_MULTIPLE = web.web_session.session_allow_multiple()


def normalize_host(host: str | None) -> str:
    web = _web()
    return web.web_session.normalize_host(host, default_host=web.HOST)
