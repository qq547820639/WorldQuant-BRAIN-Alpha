"""Web candidate, check, submit and preflight bindings."""

from __future__ import annotations

from ._helpers import _app_context, _runtime_facade


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
