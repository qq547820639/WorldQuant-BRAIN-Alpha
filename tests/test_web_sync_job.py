from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_sync_job import run_sync_job_service


class Store:
    def __init__(self):
        self.updates = []

    def update(self, job_id, **kwargs):
        self.updates.append({"job_id": job_id, **kwargs})


class Api:
    def __init__(self, fail_auth=False, fail_context=False):
        self.fail_auth = fail_auth
        self.fail_context = fail_context

    def authenticate(self):
        if self.fail_auth:
            raise RuntimeError("auth failed")
        return {"ok": True}

    def list_user_alphas(self, sync_range, progress_callback=None):
        if progress_callback:
            progress_callback({"scanned": 1, "total": 2, "page_size": 1, "offset": 0})
        return [{"id": "a1"}, {"id": "a2"}]

    def list_fields(self, *_args, progress_callback=None):
        if self.fail_context:
            raise RuntimeError("context failed")
        if progress_callback:
            progress_callback({"scanned": 1, "total": 1})
        return [{"id": "close", "dataset": {"id": "fundamental", "name": "Fundamental"}}]

    def list_operators(self, *_args, progress_callback=None):
        if progress_callback:
            progress_callback({"scanned": 1, "total": 1})
        return [{"name": "rank"}]


class Repo:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir

    def merge_cloud_alphas(self, rows, sync_range):
        return {"added": len(rows), "updated": 0, "skipped": 0, "failed": 0}


def test_run_sync_job_service_completes_and_persists_context(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    persisted = []

    run_sync_job_service(
        "sync_1",
        {"syncRange": "7d"},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: Api(),
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
        persist_official_context=lambda fields, operators, datasets: persisted.append((fields, operators, datasets)),
        default_fields=[{"id": "fallback_field"}],
        default_operators=[{"name": "fallback_operator"}],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert store.updates[-1]["status"] == "completed"
    result = store.updates[-1]["result"]
    assert result["range"] == "7d"
    assert result["count"] == 2
    assert result["fields_count"] == 1
    assert persisted[0][1] == [{"name": "rank"}]


def test_run_sync_job_service_marks_failed_on_auth_error(tmp_path):
    run_config = RunConfig(environment="mock")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()

    run_sync_job_service(
        "sync_1",
        {},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: Api(fail_auth=True),
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[],
        default_operators=[],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert store.updates[-1]["status"] == "failed"
    assert store.updates[-1]["progress"]["error_context"]["error_code"] == "SYNC_JOB_FAILED"
