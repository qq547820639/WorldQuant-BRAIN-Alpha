from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_check_batch_job import run_check_batch_job_service


class Store:
    def __init__(self):
        self.updates = []

    def update(self, job_id, **kwargs):
        self.updates.append({"job_id": job_id, **kwargs})


class Api:
    def __init__(self, fail_auth=False):
        self.fail_auth = fail_auth

    def authenticate(self):
        if self.fail_auth:
            raise RuntimeError("auth failed")
        return {"ok": True}


class Repo:
    def __init__(self, storage_dir, records):
        self.storage_dir = storage_dir
        self.records = records

    def save_check_record(self, row):
        self.records.append(dict(row))


class Ledger:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir


def test_run_check_batch_job_service_updates_counts_and_persists(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    records = []
    candidates = [{"alpha_id": "a1"}, {"alpha_id": "a2"}, {"alpha_id": "a3"}]

    def check_candidate(candidate, *_args, **_kwargs):
        if candidate["alpha_id"] == "a1":
            return {"ok": True, "alpha_id": "a1", "submittable": True}
        if candidate["alpha_id"] == "a2":
            return {"ok": False, "alpha_id": "a2", "error": "bad"}
        return {"ok": True, "alpha_id": "a3", "passed": False}

    run_check_batch_job_service(
        "check_1",
        {"job_id": "source_1", "refreshCloudForCheck": True},
        store=store,
        passed_candidates_from_payload=lambda payload: candidates,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: Api(),
        repository_factory=lambda storage_dir: Repo(storage_dir, records),
        ledger_factory=Ledger,
        refresh_cloud_context_for_check=lambda *args, **kwargs: ([{"id": "cloud_1"}], ""),
        payload_truthy=bool,
        check_candidate_availability=check_candidate,
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert store.updates[-1]["status"] == "completed"
    summary = store.updates[-1]["result"]["summary"]
    assert summary["checked"] == 3
    assert summary["submittable"] == 1
    assert summary["failed"] == 1
    assert summary["blocked"] == 1
    assert [row["alpha_id"] for row in records] == ["a1", "a2", "a3"]
    assert records[0]["job_id"] == "source_1"


def test_run_check_batch_job_service_marks_failed_on_exception(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()

    run_check_batch_job_service(
        "check_1",
        {},
        store=store,
        passed_candidates_from_payload=lambda payload: [{"alpha_id": "a1"}],
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: Api(fail_auth=True),
        repository_factory=lambda storage_dir: Repo(storage_dir, []),
        ledger_factory=Ledger,
        refresh_cloud_context_for_check=lambda *args, **kwargs: ([], ""),
        payload_truthy=bool,
        check_candidate_availability=lambda *args, **kwargs: {"ok": True},
        observability_submission_preflight=lambda storage_dir: {},
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert store.updates[-1]["status"] == "failed"
    assert store.updates[-1]["error"] == "auth failed"
    assert store.updates[-1]["progress"]["error_context"]["error_code"] == "CHECK_BATCH_JOB_FAILED"
