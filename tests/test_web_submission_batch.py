from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_submission_batch import submit_batch_payload


def test_submit_batch_payload_blocks_on_observability_confirmation(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    advisory = {"requires_confirmation": True, "blocking_flags": ["rate_limit_pressure"]}

    payload = submit_batch_payload(
        {"alpha_ids": ["a1"], "confirm_submit": True},
        run_config_from_payload=lambda body: run_config,
        observability_submission_preflight=lambda storage_dir: advisory,
        submit_candidate=lambda body: {"ok": True},
        candidate_from_payload=lambda body: {},
        web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
        payload_truthy=bool,
    )

    assert payload["ok"] is False
    assert payload["schema_version"] == "submission_batch_result.v2"
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED"
    assert payload["observability_preflight"]["blocking_flags"] == ["rate_limit_pressure"]


def test_submit_batch_payload_requires_explicit_submit_confirmation(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    submitted = []

    payload = submit_batch_payload(
        {"alpha_ids": ["a1"]},
        run_config_from_payload=lambda body: run_config,
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
        submit_candidate=lambda body: submitted.append(body) or {"ok": True},
        candidate_from_payload=lambda body: {"alpha_id": body["alpha_id"]},
        web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
        payload_truthy=bool,
    )

    assert payload["ok"] is False
    assert payload["schema_version"] == "submission_batch_result.v2"
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "SUBMIT_CONFIRMATION_REQUIRED"
    assert payload["state_navigation"]["reason_code"] == "SUBMIT_CONFIRMATION_REQUIRED"
    assert submitted == []


def test_submit_batch_payload_blocks_all_candidates_on_candidate_preflight(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    submitted = []

    payload = submit_batch_payload(
        {
            "alpha_ids": ["a1", "a2"],
            "submit_candidates": [
                {"alpha_id": "a1", "official_alpha_id": "off_1"},
                {"alpha_id": "a2"},
            ],
            "confirm_submit": True,
        },
        run_config_from_payload=lambda body: run_config,
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
        submit_candidate=lambda body: submitted.append(body) or {"ok": True},
        candidate_from_payload=lambda body: {"alpha_id": body["alpha_id"]},
        web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
        payload_truthy=bool,
        submission_preflight_advisory=lambda candidate, config: (
            {"ok": False, "error_code": "MISSING_OFFICIAL_ID", "error": "missing official"}
            if candidate.get("alpha_id") == "a2"
            else {"ok": True}
        ),
    )

    assert payload["ok"] is False
    assert payload["schema_version"] == "submission_batch_result.v2"
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "SUBMIT_BATCH_PREFLIGHT_FAILED"
    assert payload["blocked_candidates"] == [
        {
            "alpha_id": "a2",
            "official_alpha_id": "",
            "error_code": "MISSING_OFFICIAL_ID",
            "error": "missing official",
            "action": "",
        }
    ]
    assert payload["state_counts"]["MISSING_OFFICIAL_ID"] == 1
    assert submitted == []


def test_submit_batch_payload_deduplicates_successful_alpha_ids(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    submitted = []

    def submit_candidate(body):
        submitted.append(body["alpha_id"])
        return {"ok": True, "submission": {"status": "SUBMITTED"}}

    payload = submit_batch_payload(
        {"alpha_ids": ["a1", "a1"], "submit_candidates": [{"alpha_id": "a1"}], "confirm_submit": True},
        run_config_from_payload=lambda body: run_config,
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
        submit_candidate=submit_candidate,
        candidate_from_payload=lambda body: {"alpha_id": body["alpha_id"]},
        web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
        payload_truthy=bool,
    )

    assert payload["ok"] is True
    assert payload["schema_version"] == "submission_batch_result.v2"
    assert payload["status"] == "COMPLETED"
    assert payload["submitted"] == 1
    assert payload["failed"] == 0
    assert payload["submitted_alpha_ids"] == ["a1"]
    assert payload["state_counts"]["SUBMITTED"] == 1
    assert payload["state_counts"]["ALREADY_SUBMITTED"] == 1
    assert submitted == ["a1"]
    assert payload["results"][1]["submission"]["status"] == "ALREADY_SUBMITTED"
