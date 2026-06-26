import logging
from pathlib import Path

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_cloud.sync_payload import sync_cloud_alphas_payload


class Api:
    def __init__(self, fail_context=False, fail_datasets=False):
        self.fail_context = fail_context
        self.fail_datasets = fail_datasets
        self.sync_ranges = []

    def authenticate(self):
        return {"ok": True}

    def list_user_alphas(self, sync_range):
        self.sync_ranges.append(sync_range)
        return [{"id": "a1"}, {"id": "a2"}]

    def list_fields(self, *_args):
        if self.fail_context:
            raise RuntimeError("context failed")
        return [{"id": "close", "dataset": {"id": "fundamental"}}]

    def list_operators(self, *_args):
        return [{"name": "rank"}]

    def list_datasets(self, *_args):
        if self.fail_datasets:
            raise RuntimeError("datasets failed")
        return [{"id": "official_ds", "name": "Official Dataset", "field_count": 9}]


class ApiWithDatasets(Api):
    def list_datasets(self, *_args):
        return [{"id": "official_ds", "name": "Official Dataset", "field_count": 9}]


class Repo:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir

    def merge_cloud_alphas(self, rows, sync_range):
        return {"added": len(rows), "updated": 1, "skipped": 0, "failed": 0}


def test_sync_modules_keep_single_job_and_payload_owners():
    sync_job_dir = Path("brain_alpha_ops/web_cloud/sync_job")
    sync_job_source = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(sync_job_dir.rglob("*.py"))
    )
    sync_payload_source = Path("brain_alpha_ops/web_cloud/sync_payload.py").read_text(encoding="utf-8")
    handler_source = Path("brain_alpha_ops/web/handlers/sync.py").read_text(encoding="utf-8")

    assert sync_job_source.count("def run_sync_job_service(") == 1
    assert "def sync_cloud_alphas_payload(" not in sync_job_source
    assert sync_payload_source.count("def sync_cloud_alphas_payload(") == 1
    assert "def run_sync_job_service(" not in sync_payload_source
    assert "from brain_alpha_ops.web_cloud.sync_job import" in handler_source
    assert "from brain_alpha_ops.web_cloud.sync_payload import sync_cloud_alphas_payload" in handler_source
    assert "def " not in handler_source


def test_sync_cloud_alphas_payload_merges_and_persists_context(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    persisted = []

    payload = sync_cloud_alphas_payload(
        {"syncRange": "7d"},
        run_config_from_payload=lambda body: run_config,
        api_from_run_config=lambda config: Api(),
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [{"id": "fundamental", "field_count": len(fields)}],
        persist_official_context=lambda fields, operators, datasets: persisted.append((fields, operators, datasets)),
        default_fields=[],
        default_operators=[],
    )

    assert payload["ok"] is True
    assert payload["range"] == "7d"
    assert payload["count"] == 2
    assert payload["status"] == "completed"
    assert payload["fields_count"] == 1
    assert payload["operators_count"] == 1
    assert payload["context_status"] == "refreshed"
    assert payload["context_warnings"] == []
    assert persisted


def test_sync_cloud_alphas_payload_prefers_official_datasets(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    persisted = []
    api = ApiWithDatasets()

    payload = sync_cloud_alphas_payload(
        {},
        run_config_from_payload=lambda body: run_config,
        api_from_run_config=lambda config: api,
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [{"id": "derived"}],
        persist_official_context=lambda fields, operators, datasets: persisted.append((fields, operators, datasets)),
        default_fields=[],
        default_operators=[],
    )

    assert api.sync_ranges == ["all"]
    assert payload["range"] == "all"
    assert payload["datasets_count"] == 1
    assert persisted[0][2] == [{"id": "official_ds", "name": "Official Dataset", "field_count": 9}]


def test_sync_cloud_alphas_payload_uses_all_when_request_omits_range_even_if_config_is_short(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.cloud_sync_range = "3d"
    api = Api()

    payload = sync_cloud_alphas_payload(
        {},
        run_config_from_payload=lambda body: run_config,
        api_from_run_config=lambda config: api,
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[],
        default_operators=[],
    )

    assert api.sync_ranges == ["all"]
    assert payload["range"] == "all"


def test_sync_cloud_alphas_payload_uses_context_fallback(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)

    payload = sync_cloud_alphas_payload(
        {},
        run_config_from_payload=lambda body: run_config,
        api_from_run_config=lambda config: Api(fail_context=True),
        repository_factory=Repo,
        datasets_from_fields=lambda fields: [],
        persist_official_context=lambda fields, operators, datasets: None,
        default_fields=[{"id": "fallback"}],
        default_operators=[{"name": "fallback_op"}],
    )

    assert payload["fields_count"] == 1
    assert payload["operators_count"] == 1
    assert payload["datasets_count"] == 0
    assert payload["status"] == "completed_with_warnings"
    assert payload["context_status"] == "fallback"
    assert payload["context_error"] == "context failed"


def test_sync_cloud_alphas_payload_logs_context_failure(tmp_path, caplog):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.web_sync_payload"):
        payload = sync_cloud_alphas_payload(
            {},
            run_config_from_payload=lambda body: run_config,
            api_from_run_config=lambda config: Api(fail_context=True),
            repository_factory=Repo,
            datasets_from_fields=lambda fields: [],
            persist_official_context=lambda fields, operators, datasets: None,
            default_fields=[{"id": "fallback"}],
            default_operators=[{"name": "fallback_op"}],
        )

    assert payload["fields_count"] == 1
    assert payload["operators_count"] == 1
    assert "official context sync failed; falling back to default fields/operators" in caplog.text
    assert "context failed" in caplog.text


def test_sync_cloud_alphas_payload_reports_dataset_fallback_warning(tmp_path, caplog):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    persisted = []

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.web_sync_payload"):
        payload = sync_cloud_alphas_payload(
            {},
            run_config_from_payload=lambda body: run_config,
            api_from_run_config=lambda config: Api(fail_datasets=True),
            repository_factory=Repo,
            datasets_from_fields=lambda fields: [{"id": "derived", "field_count": len(fields)}],
            persist_official_context=lambda fields, operators, datasets: persisted.append((fields, operators, datasets)),
            default_fields=[],
            default_operators=[],
        )

    assert payload["status"] == "completed_with_warnings"
    assert payload["context_status"] == "refreshed_with_warnings"
    assert payload["context_warnings"] == [
        "official datasets API unavailable; deriving datasets from fields: datasets failed"
    ]
    assert persisted[0][2] == [{"id": "derived", "field_count": 1}]
    assert "official datasets API unavailable; deriving datasets from fields" in caplog.text
