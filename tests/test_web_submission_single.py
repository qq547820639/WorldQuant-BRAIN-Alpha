from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_submission_single import submit_candidate_payload


class FakeApi:
    def __init__(self, calls):
        self.calls = calls

    def authenticate(self):
        self.calls.append(("authenticate",))
        return {"ok": True}

    def submit_alpha(self, alpha_id, expression, settings):
        self.calls.append(("submit_alpha", alpha_id, expression, settings))
        return {"status": "SUBMITTED", "alpha_id": alpha_id}


class FakeLedger:
    def __init__(self, storage_dir, records):
        self.storage_dir = storage_dir
        self.records = records

    def record(self, candidate, result, mode):
        self.records.append({"candidate": candidate.alpha_id, "result": dict(result), "mode": mode})


class FakeRepository:
    def __init__(self, storage_dir, records):
        self.storage_dir = storage_dir
        self.records = records

    def save_lifecycle_record(self, job_id, row):
        self.records.append({"job_id": job_id, "row": dict(row)})


def _candidate():
    return {
        "alpha_id": "a1",
        "official_alpha_id": "off_1",
        "expression": "rank(close)",
        "family": "demo",
        "hypothesis": "demo",
        "gate": {"submission_ready": True},
        "lifecycle_status": "submission_ready",
    }


def test_submit_candidate_payload_submits_and_records(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    api_calls = []
    ledger_records = []
    lifecycle_records = []

    payload = submit_candidate_payload(
        {"candidate": _candidate(), "job_id": "job_1", "submit_mode": "manual"},
        candidate_from_payload=lambda body: body["candidate"],
        run_config_from_payload=lambda body: run_config,
        submission_preflight_advisory=lambda candidate, config: {"ok": True},
        record_submit_blocked=lambda payload, candidate, config, reason: None,
        official_alpha_id=lambda candidate: candidate["official_alpha_id"],
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
        payload_truthy=bool,
        api_from_run_config=lambda config: FakeApi(api_calls),
        ledger_factory=lambda storage_dir: FakeLedger(storage_dir, ledger_records),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, lifecycle_records),
    )

    assert payload["ok"] is True
    assert payload["schema_version"] == "submission_result.v2"
    assert payload["alpha_id"] == "a1"
    assert payload["official_alpha_id"] == "off_1"
    assert payload["status"] == "SUBMITTED"
    assert payload["submission"]["status"] == "SUBMITTED"
    assert api_calls[0] == ("authenticate",)
    assert api_calls[1][0] == "submit_alpha"
    assert ledger_records[0]["candidate"] == "a1"
    assert lifecycle_records[0]["job_id"] == "job_1"
    assert lifecycle_records[0]["row"]["stage"] == "submitted"


def test_submit_candidate_payload_records_preflight_block(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    blocked = []

    payload = submit_candidate_payload(
        {"candidate": _candidate()},
        candidate_from_payload=lambda body: body["candidate"],
        run_config_from_payload=lambda body: run_config,
        submission_preflight_advisory=lambda candidate, config: {"ok": False, "error": "blocked"},
        record_submit_blocked=lambda body, candidate, config, reason: blocked.append(reason),
        official_alpha_id=lambda candidate: candidate["official_alpha_id"],
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
        payload_truthy=bool,
        api_from_run_config=lambda config: FakeApi([]),
    )

    assert payload["ok"] is False
    assert payload["error"] == "blocked"
    assert payload["schema_version"] == "submission_result.v2"
    assert payload["alpha_id"] == "a1"
    assert payload["status"] == "BLOCKED"
    assert blocked == ["blocked"]
