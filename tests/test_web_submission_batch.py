from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_submission_batch import submit_batch_payload


def test_submit_batch_payload_blocks_on_observability_confirmation(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    advisory = {"requires_confirmation": True, "blocking_flags": ["rate_limit_pressure"]}

    payload = submit_batch_payload(
        {"alpha_ids": ["a1"]},
        run_config_from_payload=lambda body: run_config,
        observability_submission_preflight=lambda storage_dir: advisory,
        submit_candidate=lambda body: {"ok": True},
        candidate_from_payload=lambda body: {},
        web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
        payload_truthy=bool,
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED"
    assert payload["observability_preflight"]["blocking_flags"] == ["rate_limit_pressure"]


def test_submit_batch_payload_deduplicates_successful_alpha_ids(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    submitted = []

    def submit_candidate(body):
        submitted.append(body["alpha_id"])
        return {"ok": True, "submission": {"status": "SUBMITTED"}}

    payload = submit_batch_payload(
        {"alpha_ids": ["a1", "a1"], "submit_candidates": [{"alpha_id": "a1"}]},
        run_config_from_payload=lambda body: run_config,
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
        submit_candidate=submit_candidate,
        candidate_from_payload=lambda body: {"alpha_id": body["alpha_id"]},
        web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
        payload_truthy=bool,
    )

    assert payload["ok"] is True
    assert payload["submitted"] == 2
    assert payload["failed"] == 0
    assert submitted == ["a1"]
    assert payload["results"][1]["submission"]["status"] == "ALREADY_SUBMITTED"
