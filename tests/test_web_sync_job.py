import logging

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web.handlers import sync as active_sync_handler
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
        self.sync_ranges = []

    def authenticate(self):
        if self.fail_auth:
            raise RuntimeError("auth failed")
        return {"ok": True}

    def list_user_alphas(self, sync_range, progress_callback=None):
        self.sync_ranges.append(sync_range)
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


class ForceRefreshApi(Api):
    def __init__(self):
        super().__init__()
        self.force_refresh_values = []

    def list_user_alphas(self, sync_range, progress_callback=None, *, force_refresh=False):
        self.sync_ranges.append(sync_range)
        self.force_refresh_values.append(force_refresh)
        if progress_callback:
            progress_callback({"scanned": 1, "total": 1, "page_size": 1, "offset": 0})
        return [{"id": "fresh_remote_a1"}]


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


class ObservableScanApi(Api):
    def list_user_alphas(self, sync_range, progress_callback=None):
        self.sync_ranges.append(sync_range)
        rows = [{"id": "a1"}, {"id": "a2"}]
        if progress_callback:
            progress_callback({
                "scanned": 1,
                "total": 2,
                "page_size": 1,
                "page_limit": 1,
                "offset": 0,
                "next_offset": 1,
                "page_number": 1,
                "pages_fetched": 1,
                "expected_pages": 2,
                "api_reported_total": 2,
                "remaining_items": 1,
                "has_more": True,
                "pagination_complete": False,
                "pagination_target": "api_filter_window",
                "warning": "offset_limit_narrowed_by_date",
                "cursor_before": "2026-01-01T00:00:00Z",
                "new_unique_items": 1,
                "duplicate_unique_items": 0,
                "unique_items": 1,
                "stalled_unique_pages": 0,
                "retry_attempt": 1,
                "retry_after_seconds": 5.0,
                "error_status": 504,
            })
            progress_callback({
                "scanned": 2,
                "total": 2,
                "page_size": 1,
                "page_limit": 1,
                "offset": 1,
                "next_offset": 2,
                "page_number": 2,
                "pages_fetched": 2,
                "expected_pages": 2,
                "api_reported_total": 2,
                "remaining_items": 0,
                "pagination_target": "api_filter_window",
                "has_more": True,
                "pagination_complete": False,
                "new_unique_items": 1,
                "duplicate_unique_items": 0,
                "unique_items": 2,
                "stalled_unique_pages": 0,
            })
        return rows


class ReportedTotalDiffersApi(Api):
    def list_user_alphas(self, sync_range, progress_callback=None):
        self.sync_ranges.append(sync_range)
        rows = [{"id": "a1"}, {"id": "a2"}]
        if progress_callback:
            progress_callback({"scanned": 2, "total": 12, "api_reported_total": 10, "page_size": 2, "offset": 0})
        return rows


class WaitingFirstPageApi(Api):
    def list_user_alphas(self, sync_range, progress_callback=None):
        self.sync_ranges.append(sync_range)
        if progress_callback:
            progress_callback({"scanned": 0, "total": 10000, "page_size": 0, "offset": 0})
        return []


class Repo:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir

    def merge_cloud_alphas(self, rows, sync_range):
        return {"added": len(rows), "updated": 0, "skipped": 0, "failed": 0}


class NoChangeRepo(Repo):
    def merge_cloud_alphas(self, rows, sync_range):
        return {"added": 0, "updated": 0, "skipped": len(rows), "failed": 0}


def _assert_context_only_updates(store: Store) -> None:
    assert store.updates[-1]["status"] == "completed"
    assert store.updates[-1]["result"]["context_only"] is True
    assert store.updates[-1]["result"]["count"] == 0
    assert store.updates[-1]["result"]["alphas"] == []
    for update in store.updates:
        progress = update.get("progress") or {}
        if progress:
            assert progress["context_only"] is True


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


def test_run_sync_job_service_explains_no_change_sync_is_current(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()

    run_sync_job_service(
        "sync_1",
        {"syncRange": "7d"},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: Api(),
        repository_factory=NoChangeRepo,
        datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[{"id": "fallback_field"}],
        default_operators=[{"name": "fallback_operator"}],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    progress = store.updates[-1]["progress"]
    assert store.updates[-1]["status"] == "completed"
    assert "云端数据无变化，本地缓存已是最新" in progress["status_message"]
    assert progress["message"] == progress["status_message"]


def test_timing_payload_estimates_remaining_time_from_scan_rate():
    payload = _timing_payload(100.0, done=25, total=100, now=110.0)

    assert payload["elapsed_seconds"] == 10.0
    assert payload["rate_per_second"] == 2.5
    assert payload["eta_seconds"] == 30
    assert payload["eta_deadline_at_ms"] == 140000


def test_timing_payload_can_report_rate_without_completion_target():
    payload = _timing_payload(100.0, done=25, now=110.0)

    assert payload["elapsed_seconds"] == 10.0
    assert payload["rate_per_second"] == 2.5
    assert "eta_seconds" not in payload
    assert "eta_deadline_at_ms" not in payload


def test_run_sync_job_service_defaults_to_all_cloud_alphas(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    api = Api()

    run_sync_job_service(
        "sync_default_all",
        {},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: api,
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[],
        default_operators=[],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert api.sync_ranges == ["all"]
    assert store.updates[-1]["result"]["range"] == "all"


def test_run_sync_job_service_uses_all_when_request_omits_range_even_if_config_is_short(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.cloud_sync_range = "3d"
    store = Store()
    api = Api()

    run_sync_job_service(
        "sync_config_short",
        {},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: api,
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[],
        default_operators=[],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert api.sync_ranges == ["all"]
    assert store.updates[-1]["result"]["range"] == "all"


def test_run_sync_job_service_forces_remote_user_alpha_refresh_when_supported(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    api = ForceRefreshApi()

    run_sync_job_service(
        "sync_force_refresh",
        {},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: api,
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[],
        default_operators=[],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert api.sync_ranges == ["all"]
    assert api.force_refresh_values == [True]
    assert store.updates[-1]["result"]["count"] == 1


def test_run_sync_job_service_context_only_skips_alpha_scan_and_merge(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    api = Api()
    persisted = []

    run_sync_job_service(
        "sync_context_only",
        {"contextOnly": True},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: api,
        repository_factory=lambda storage_dir: (_ for _ in ()).throw(AssertionError("merge should not run")),
        datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
        persist_official_context=lambda fields, operators, datasets: persisted.append((fields, operators, datasets)),
        default_fields=[],
        default_operators=[],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert api.sync_ranges == []
    assert persisted
    _assert_context_only_updates(store)


def test_active_sync_handler_context_only_skips_alpha_scan_and_merge(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    api = Api()
    persisted = []

    active_sync_handler.run_sync_job_service(
        "sync_context_only_active",
        {"context_only": True},
        store=store,
        run_config_from_payload=lambda payload: run_config,
        api_from_run_config=lambda config: api,
        repository_factory=lambda storage_dir: (_ for _ in ()).throw(AssertionError("merge should not run")),
        datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
        persist_official_context=lambda fields, operators, datasets: persisted.append((fields, operators, datasets)),
        default_fields=[],
        default_operators=[],
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert api.sync_ranges == []
    assert persisted
    _assert_context_only_updates(store)


def test_run_sync_job_service_persists_scan_observability_without_stale_warning(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    api = ObservableScanApi()

    run_sync_job_service(
        "sync_observable",
        {},
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

    scan_progress = [
        update["progress"]
        for update in store.updates
        if (update.get("progress") or {}).get("status_code") == "SCAN"
    ]
    assert scan_progress[0]["page_number"] == 1
    assert scan_progress[0]["pages_fetched"] == 1
    assert scan_progress[0]["expected_pages"] == 2
    assert scan_progress[0]["api_reported_total"] == 2
    assert "total" not in scan_progress[0]
    assert scan_progress[0]["remaining_items"] == 1
    assert scan_progress[0]["has_more"] is True
    assert scan_progress[0]["pagination_complete"] is False
    assert scan_progress[0]["pagination_target"] == "api_filter_window"
    assert scan_progress[0]["page_limit"] == 1
    assert scan_progress[0]["next_offset"] == 1
    assert scan_progress[0]["warning"] == "offset_limit_narrowed_by_date"
    assert scan_progress[0]["cursor_before"] == "2026-01-01T00:00:00Z"
    assert scan_progress[0]["new_unique_items"] == 1
    assert scan_progress[0]["duplicate_unique_items"] == 0
    assert scan_progress[0]["unique_items"] == 1
    assert scan_progress[0]["stalled_unique_pages"] == 0
    assert scan_progress[0]["retry_attempt"] == 1
    assert scan_progress[0]["retry_after_seconds"] == 5.0
    assert scan_progress[0]["error_status"] == 504
    assert scan_progress[0]["status_message"] == (
        "正在扫描云端 Alpha；已拉取 1 条；接口分页参考数 2 条；当前第 1 页；"
        "分页参数 1 条/页；本页 1 条；下一轮继续拉取；已自动缩小时间范围。"
    )
    assert "1/2" not in scan_progress[0]["status_message"]
    assert "1 / 2" not in scan_progress[0]["status_message"]
    assert "eta_seconds" not in scan_progress[0]
    assert "eta_deadline_at_ms" not in scan_progress[0]
    assert "percent_complete" not in scan_progress[0]
    assert scan_progress[1]["page_number"] == 2
    assert scan_progress[1]["remaining_items"] == 0
    assert scan_progress[1]["has_more"] is True
    assert scan_progress[1]["pagination_complete"] is False
    assert "stop_reason" not in scan_progress[1]
    assert scan_progress[1]["unique_items"] == 2
    assert "warning" not in scan_progress[1]
    assert "cursor_before" not in scan_progress[1]
    assert "retry_attempt" not in scan_progress[1]


def test_run_sync_job_service_does_not_count_down_against_reported_total_after_scan(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    api = ReportedTotalDiffersApi()

    run_sync_job_service(
        "sync_report_reference",
        {},
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

    context_updates = [
        update["progress"]
        for update in store.updates
        if (update.get("progress") or {}).get("status_code") == "CONTEXT_FIELDS"
    ]
    initial_context = context_updates[0]
    assert initial_context["scanned"] == 2
    assert initial_context["total"] == 2
    assert initial_context["api_reported_total"] == 10
    assert initial_context["filter_window_count"] == 10
    assert "eta_seconds" not in initial_context
    assert "eta_deadline_at_ms" not in initial_context

    final = store.updates[-1]
    assert final["status"] == "completed"
    assert final["result"]["count"] == 2
    assert final["result"]["total"] == 2
    assert final["result"]["api_reported_total"] == 10
    assert final["result"]["filter_window_count"] == 10
    assert "eta_seconds" not in final["result"]
    assert "eta_deadline_at_ms" not in final["result"]
    assert "eta_seconds" not in final["progress"]
    assert "eta_deadline_at_ms" not in final["progress"]


def test_run_sync_job_service_guides_first_page_wait_without_completion_total(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    api = WaitingFirstPageApi()

    run_sync_job_service(
        "sync_first_page_wait",
        {},
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

    scan_progress = [
        update["progress"]
        for update in store.updates
        if (update.get("progress") or {}).get("status_code") == "SCAN"
    ]
    assert "3-5 分钟" in scan_progress[0]["status_message"]
    assert "近 3/7 天范围通常更快" in scan_progress[0]["status_message"]
    assert "total" not in scan_progress[0]


def test_active_sync_handler_scan_uses_filter_window_not_progress_total(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    store = Store()
    api = ObservableScanApi()

    active_sync_handler.run_sync_job_service(
        "sync_active_observable",
        {},
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

    scan_progress = [
        update["progress"]
        for update in store.updates
        if (update.get("progress") or {}).get("status_code") == "SCAN"
    ]
    assert scan_progress[0]["api_reported_total"] == 2
    assert scan_progress[0]["filter_window_count"] == 2
    assert "total" not in scan_progress[0]
    assert scan_progress[0]["pagination_target"] == "api_filter_window"
    assert "接口分页参考数 2 条" in scan_progress[0]["status_message"]
    assert "1 / 2" not in scan_progress[0]["status_message"]

    final = store.updates[-1]
    assert final["status"] == "completed"
    assert final["result"]["total"] == 2
    assert final["result"]["api_reported_total"] == 2
    assert final["result"]["filter_window_count"] == 2


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

    assert store.updates[-1]["status"] == "cancelled"  # P0-2 unified
    assert store.updates[-1]["progress"]["status_code"] == "STOPPED"
    assert store.updates[-1]["result"]["status"] == "cancelled"  # P0-2 unified


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
    assert store.updates[-1]["status"] == "cancelled"  # P0-2 unified
    assert store.updates[-1]["progress"]["status_code"] == "STOPPED"


def test_run_sync_job_service_ignores_elapsed_limit_and_scans_all_pages(tmp_path):
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

    assert api.pages_requested == 3
    assert api.callback_results == [True, True, True]
    assert store.updates[-1]["status"] == "completed"
    assert store.updates[-1]["result"]["count"] == 3
