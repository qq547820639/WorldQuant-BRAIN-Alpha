import logging

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_sync_job import _timing_payload, run_sync_job_service


class Store:
    def __init__(self):
        self.updates = []
        self.cancelled = False

    def update(self, job_id, **kwargs):
        self.updates.append({"job_id": job_id, **kwargs})

    def is_cancelled(self, _job_id):
        return self.cancelled


class CancelAfterScanStore(Store):
    def update(self, job_id, **kwargs):
        super().update(job_id, **kwargs)
        progress = kwargs.get("progress") or {}
        if progress.get("status_code") == "SCAN":
            self.cancelled = True


class Api:
    def __init__(self, fail_auth=False, fail_context=False, fail_datasets=False):
        self.fail_auth = fail_auth
        self.fail_context = fail_context
        self.fail_datasets = fail_datasets

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

    def list_datasets(self, *_args):
        if self.fail_datasets:
            raise RuntimeError("datasets failed")
        return [{"id": "fundamental", "name": "Fundamental"}]


class CancellableScanApi(Api):
    def __init__(self):
        super().__init__()
        self.pages_requested = 0
        self.callback_results = []

    def list_user_alphas(self, sync_range, progress_callback=None):
        rows = []
        for page in range(3):
            self.pages_requested += 1
            rows.append({"id": f"a{page + 1}"})
            if progress_callback:
                keep_going = progress_callback({
                    "scanned": len(rows),
                    "total": 300,
                    "page_size": 1,
                    "offset": page,
                })
                self.callback_results.append(keep_going)
                if keep_going is False:
                    break
        return rows


class Repo:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir

    def merge_cloud_alphas(self, rows, sync_range):
        return {"added": len(rows), "updated": 0, "skipped": 0, "failed": 0}


def test_run_sync_job_service_completes_and_persists_context(tmp_path):
    run_config = RunConfig(environment="production")
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
    assert store.updates[-1]["progress"]["started_at_ms"] > 0
    assert "updated_at_ms" in store.updates[-1]["progress"]


def test_timing_payload_estimates_remaining_time_from_scan_rate():
    payload = _timing_payload(100.0, done=25, total=100, now=110.0)

    assert payload["elapsed_seconds"] == 10.0
    assert payload["rate_per_second"] == 2.5
    assert payload["eta_seconds"] == 30
    assert payload["eta_deadline_at_ms"] == 140000


def test_run_sync_job_service_marks_failed_on_auth_error(tmp_path):
    run_config = RunConfig(environment="production")
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


def test_run_sync_job_service_marks_context_failure_as_warning(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()

    run_sync_job_service(
        "sync_1",
        {"syncRange": "7d"},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: Api(fail_context=True),
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [{"id": "unused"}],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[{"id": "fallback_field"}],
        default_operators=[{"name": "fallback_operator"}],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    final = store.updates[-1]
    assert final["status"] == "completed_with_warnings"
    assert final["result"]["context_status"] == "failed"
    assert final["result"]["context_error"] == "context failed"
    assert final["result"]["fields_count"] == 1
    assert final["progress"]["status_code"] == "COMPLETED_WITH_WARNINGS"


def test_run_sync_job_service_logs_dataset_fallback_warning(tmp_path, caplog):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    persisted = []

    with caplog.at_level(logging.WARNING):
        run_sync_job_service(
            "sync_1",
            {"syncRange": "7d"},
            store=store,
            run_config_from_payload=lambda payload: run_config,
            api_from_run_config=lambda config: Api(fail_datasets=True),
            repository_factory=Repo,
            datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
            persist_official_context=lambda fields, operators, datasets: persisted.append((fields, operators, datasets)),
            default_fields=[{"id": "fallback_field"}],
            default_operators=[{"name": "fallback_operator"}],
            safe_error_message=str,
            error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
        )

    assert store.updates[-1]["status"] == "completed_with_warnings"
    assert persisted[0][2] == [{"id": "fundamental", "field_count": 1}]
    assert store.updates[-1]["result"]["context_status"] == "refreshed_with_warnings"
    assert store.updates[-1]["result"]["context_warnings"] == [
        "official datasets API unavailable; deriving datasets from fields: datasets failed"
    ]
    assert "official datasets API unavailable; deriving datasets from fields" in caplog.text


def test_run_sync_job_service_honors_cancel_before_remote_calls(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    store.cancelled = True

    run_sync_job_service(
        "sync_1",
        {"syncRange": "3d"},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: Api(),
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[],
        default_operators=[],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert store.updates[-1]["status"] == "stopped"
    assert store.updates[-1]["progress"]["status_code"] == "STOPPED"
    assert store.updates[-1]["result"]["status"] == "stopped"


def test_run_sync_job_service_returns_false_to_cancel_alpha_scan(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = CancelAfterScanStore()
    api = CancellableScanApi()

    run_sync_job_service(
        "sync_1",
        {"syncRange": "3d"},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: api,
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[],
        default_operators=[],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert api.pages_requested == 1
    assert api.callback_results == [False]
    assert store.updates[-1]["status"] == "stopped"
    assert store.updates[-1]["progress"]["status_code"] == "STOPPED"


def test_run_sync_job_service_stops_alpha_scan_on_elapsed_limit(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.cloud_sync_max_elapsed_seconds = 0.000001
    store = Store()
    api = CancellableScanApi()

    run_sync_job_service(
        "sync_1",
        {"syncRange": "3d"},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: api,
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[],
        default_operators=[],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert api.pages_requested == 1
    assert api.callback_results == [False]
    assert store.updates[-1]["status"] == "stopped"
    assert store.updates[-1]["result"]["message"] == "云端同步已达到耗时上限 1e-06s。"
    assert store.updates[-1]["progress"]["status_message"] == "云端同步达到耗时上限，可缩小同步范围或稍后继续。"
