from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_candidate_check import check_candidate_payload


class FakeApi:
    def __init__(self, fail_auth=False):
        self.fail_auth = fail_auth

    def authenticate(self):
        if self.fail_auth:
            raise RuntimeError("auth failed")
        return {"ok": True}


class FakeRepository:
    def __init__(self, storage_dir, records):
        self.storage_dir = storage_dir
        self.records = records

    def save_check_record(self, row):
        self.records.append(dict(row))


class FakeLedger:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir


def test_check_candidate_payload_returns_auth_error(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)

    payload = check_candidate_payload(
        {"candidate": {"alpha_id": "a1"}},
        candidate_from_payload=lambda body: {},
        run_config_from_payload=lambda body: run_config,
        api_from_run_config=lambda config: FakeApi(fail_auth=True),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, []),
        ledger_factory=FakeLedger,
        refresh_cloud_context_for_check=lambda *args, **kwargs: ([], ""),
        payload_truthy=bool,
        check_candidate_availability=lambda *args, **kwargs: {"ok": True},
        observability_submission_preflight=lambda storage_dir: {},
        web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "AUTH_FAILED"


def test_check_candidate_payload_persists_check_result(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    records = []

    payload = check_candidate_payload(
        {"candidate": {"alpha_id": "a1"}, "job_id": "job_1", "refreshCloudForCheck": True},
        candidate_from_payload=lambda body: {},
        run_config_from_payload=lambda body: run_config,
        api_from_run_config=lambda config: FakeApi(),
        repository_factory=lambda storage_dir: FakeRepository(storage_dir, records),
        ledger_factory=FakeLedger,
        refresh_cloud_context_for_check=lambda *args, **kwargs: ([{"id": "cloud_1"}], ""),
        payload_truthy=bool,
        check_candidate_availability=lambda *args, **kwargs: {
            "ok": True,
            "alpha_id": "a1",
            "passed": True,
        },
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
        web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
    )

    assert payload["ok"] is True
    assert records == [{"job_id": "job_1", "ok": True, "alpha_id": "a1", "passed": True}]
