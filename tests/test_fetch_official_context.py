import json
import time

import pytest

import fetch_official_context
from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.config import RunConfig, write_run_config
from brain_alpha_ops.data.loader import (
    PACKAGED_OFFICIAL_CONTEXT_FILES,
    OfficialDataLoader,
    ensure_official_context_files,
)


@pytest.fixture(autouse=True)
def restore_official_loader():
    yield
    OfficialDataLoader.reload()


class FakeOfficialBrainAPI:
    def __init__(self, config, **credentials):
        self.config = config
        self.credentials = credentials

    def set_market_scope(self, settings):
        self.settings = settings

    def authenticate(self):
        return {"status": "ok", "auth": "token", "token": "redacted-by-test"}

    def list_fields(self, *_args, progress_callback=None):
        if progress_callback:
            progress_callback({"scanned": 1, "total": 1})
        return [{"id": "close", "dataset": {"id": "pv1", "name": "Price Volume"}}]

    def list_operators(self, *_args, progress_callback=None):
        if progress_callback:
            progress_callback({"scanned": 1, "total": 1})
        return [{"name": "rank"}]

    def list_datasets(self, *_args, progress_callback=None):
        if progress_callback:
            progress_callback({"scanned": 1, "total": 1})
        return [{"id": "pv1", "name": "Price Volume", "field_count": 1}]


class RateLimitedOfficialBrainAPI(FakeOfficialBrainAPI):
    def list_fields(self, *_args, progress_callback=None):
        raise BrainAPIError("HTTP 429: rate limit", status_code=429, retry_after=12)


class ServerErrorOfficialBrainAPI(FakeOfficialBrainAPI):
    def list_fields(self, *_args, progress_callback=None):
        raise BrainAPIError("HTTP 503: service unavailable", status_code=503)


class GenericFailureOfficialBrainAPI(FakeOfficialBrainAPI):
    def list_fields(self, *_args, progress_callback=None):
        raise RuntimeError("unexpected local refresh failure")


class SlowOfficialBrainAPI(FakeOfficialBrainAPI):
    def list_fields(self, *_args, progress_callback=None):
        time.sleep(2)
        return super().list_fields(*_args, progress_callback=progress_callback)


class DirectOnlyOfficialBrainAPI(FakeOfficialBrainAPI):
    last_disable_proxy: bool | None = None

    def __init__(self, config, **credentials):
        DirectOnlyOfficialBrainAPI.last_disable_proxy = credentials.pop("disable_proxy", False)
        super().__init__(config, **credentials)


def _write_config(tmp_path, monkeypatch):
    config = RunConfig(environment="production")
    config.credentials.token_env = "TEST_BRAIN_TOKEN"
    config.ops.storage_dir = str(tmp_path / "data")
    config.ops.settings.dataset = "pv1"
    config.ops.official_api.cache_dir = str(tmp_path / "api_cache")
    monkeypatch.setenv("TEST_BRAIN_TOKEN", "test-token")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    return config_path


def test_refresh_official_context_writes_context_and_status(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", FakeOfficialBrainAPI)
    config_path = _write_config(tmp_path, monkeypatch)
    status_path = tmp_path / "refresh_status.json"

    result = fetch_official_context.refresh_official_context(config_path, status_output=status_path)

    assert result["ok"] is True
    assert result["status"] == "refreshed"
    assert result["counts"] == {"fields": 1, "operators": 1, "datasets": 1}
    assert result["after"]["manifest_stale"] is False
    assert (tmp_path / "data" / "official_fields.json").is_file()
    assert (tmp_path / "data" / "official_operators.json").is_file()
    assert (tmp_path / "data" / "official_datasets.json").is_file()
    saved_status = json.loads(status_path.read_text(encoding="utf-8"))
    assert saved_status["ok"] is True
    assert "test-token" not in status_path.read_text(encoding="utf-8")


def test_refresh_official_context_no_write_fetches_without_context_files(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", FakeOfficialBrainAPI)
    config_path = _write_config(tmp_path, monkeypatch)
    status_path = tmp_path / "refresh_status.json"

    result = fetch_official_context.refresh_official_context(config_path, write=False, status_output=status_path)

    assert result["ok"] is True
    assert result["status"] == "fetched_no_write"
    assert result["write_enabled"] is False
    assert not (tmp_path / "data" / "official_fields.json").exists()
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "fetched_no_write"


def test_refresh_official_context_fails_when_written_metadata_remains_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", FakeOfficialBrainAPI)
    config_path = _write_config(tmp_path, monkeypatch)
    status_path = tmp_path / "refresh_status.json"
    snapshots = [
        {
            "fields_count": 0,
            "operators_count": 0,
            "datasets_count": 0,
            "context_cache_manifest": {"complete": True, "is_stale": True, "stale_files": ["official_fields.json"]},
        },
        {
            "fields_count": 1,
            "operators_count": 1,
            "datasets_count": 1,
            "context_cache_manifest": {"complete": True, "is_stale": True, "stale_files": ["official_fields.json"]},
        },
    ]

    def stale_counts(**_kwargs):
        return snapshots.pop(0) if snapshots else {
            "fields_count": 1,
            "operators_count": 1,
            "datasets_count": 1,
            "context_cache_manifest": {"complete": True, "is_stale": True, "stale_files": ["official_fields.json"]},
        }

    monkeypatch.setattr(fetch_official_context, "official_context_file_counts", stale_counts)

    result = fetch_official_context.refresh_official_context(config_path, status_output=status_path)
    saved_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["status"] == "refresh_incomplete"
    assert result["error_code"] == "OFFICIAL_CONTEXT_METADATA_STALE"
    assert result["after"]["manifest_stale"] is True
    assert result["freshness_findings"] == [
        {
            "code": "context_cache_metadata_stale",
            "filename": "official_fields.json",
            "message": "official_fields.json metadata is stale after official context refresh",
        }
    ]
    assert saved_status["ok"] is False
    assert saved_status["status"] == "refresh_incomplete"


def test_refresh_official_context_records_missing_credentials(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config.ops.settings.dataset = "pv1"
    config_path = tmp_path / "run_config.json"
    status_path = tmp_path / "refresh_status.json"
    write_run_config(config, config_path)

    result = fetch_official_context.refresh_official_context(config_path, status_output=status_path)

    assert result["ok"] is False
    assert result["error_code"] == "MISSING_CREDENTIALS"
    assert "environment variables" in result["error"]
    assert json.loads(status_path.read_text(encoding="utf-8"))["ok"] is False


def test_refresh_official_context_records_retryable_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", RateLimitedOfficialBrainAPI)
    config_path = _write_config(tmp_path, monkeypatch)
    status_path = tmp_path / "refresh_status.json"

    result = fetch_official_context.refresh_official_context(config_path, status_output=status_path)
    saved_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["error_code"] == "RATE_LIMITED"
    assert result["error_category"] == "rate_limit"
    assert result["retryable"] is True
    assert result["retry_after_seconds"] == 12
    assert result["next_retry_at"]
    assert saved_status["retryable"] is True


def test_refresh_official_context_records_retryable_http_5xx(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", ServerErrorOfficialBrainAPI)
    config_path = _write_config(tmp_path, monkeypatch)
    status_path = tmp_path / "refresh_status.json"

    result = fetch_official_context.refresh_official_context(config_path, status_output=status_path)
    saved_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["error_code"] == "HTTP_503"
    assert result["error_category"] == "http"
    assert result["retryable"] is True
    assert result["retry_after_seconds"] is None
    assert saved_status["error_code"] == "HTTP_503"


def test_refresh_official_context_records_generic_internal_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", GenericFailureOfficialBrainAPI)
    config_path = _write_config(tmp_path, monkeypatch)
    status_path = tmp_path / "refresh_status.json"

    result = fetch_official_context.refresh_official_context(config_path, status_output=status_path)
    saved_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["error_code"] == "OFFICIAL_CONTEXT_REFRESH_FAILED"
    assert result["error_category"] == "internal"
    assert result["retryable"] is False
    assert result["retry_after_seconds"] is None
    assert "unexpected local refresh failure" in result["error"]
    assert saved_status["error_category"] == "internal"


def test_refresh_official_context_records_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", SlowOfficialBrainAPI)
    config_path = _write_config(tmp_path, monkeypatch)
    status_path = tmp_path / "refresh_status.json"

    result = fetch_official_context.refresh_official_context(
        config_path,
        status_output=status_path,
        timeout_seconds=0.2,
    )
    saved_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["error_code"] == "OFFICIAL_CONTEXT_REFRESH_TIMEOUT"
    assert result["error_category"] == "timeout"
    assert result["retryable"] is True
    assert result["retry_after_seconds"] == 15 * 60
    assert result["timeout_seconds"] == 0.2
    assert saved_status["error_code"] == "OFFICIAL_CONTEXT_REFRESH_TIMEOUT"


def test_refresh_official_context_zero_timeout_disables_deadline(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", SlowOfficialBrainAPI)
    config_path = _write_config(tmp_path, monkeypatch)
    status_path = tmp_path / "refresh_status.json"

    result = fetch_official_context.refresh_official_context(
        config_path,
        write=False,
        status_output=status_path,
        timeout_seconds=0,
    )
    saved_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["status"] == "fetched_no_write"
    assert result["timeout_seconds"] == 0
    assert saved_status["status"] == "fetched_no_write"
    assert "error_code" not in saved_status


def test_refresh_official_context_uses_direct_official_api(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", DirectOnlyOfficialBrainAPI)
    DirectOnlyOfficialBrainAPI.last_disable_proxy = None
    config_path = _write_config(tmp_path, monkeypatch)

    result = fetch_official_context.refresh_official_context(config_path, write=False)

    assert result["ok"] is True
    assert result["status"] == "fetched_no_write"
    assert result["write_enabled"] is False
    assert result["proxy_mode"] == "direct"
    assert result["auth"]["auth"] == "token"
    assert result["counts"] == {"fields": 1, "operators": 1, "datasets": 1}
    assert DirectOnlyOfficialBrainAPI.last_disable_proxy is True


def test_refresh_official_context_can_use_system_proxy(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", DirectOnlyOfficialBrainAPI)
    DirectOnlyOfficialBrainAPI.last_disable_proxy = None
    config_path = _write_config(tmp_path, monkeypatch)

    result = fetch_official_context.refresh_official_context(config_path, write=False, disable_proxy=False)

    assert result["ok"] is True
    assert result["status"] == "fetched_no_write"
    assert result["proxy_mode"] == "system"
    assert result["counts"] == {"fields": 1, "operators": 1, "datasets": 1}
    assert DirectOnlyOfficialBrainAPI.last_disable_proxy is False


def test_official_loader_accepts_name_only_field_records(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "official_fields.json").write_text(
        json.dumps([{"name": "close"}, {"name": "volume"}]),
        encoding="utf-8",
    )

    loader = OfficialDataLoader()
    loader.load_all(data_dir)

    assert loader.field_count == 2
    assert loader.validate_field("close") is True
    assert loader.validate_field("volume") is True


def test_official_loader_maps_category_only_fields_to_dataset_category(tmp_path):
    from brain_alpha_ops.data import FieldDatasetMapper

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "official_fields.json").write_text(
        json.dumps(
            [
                {"name": "eps_revision", "category": "analyst"},
                {"name": "sales_revision", "category": "analyst"},
                {"name": "debt_ratio", "category": "fundamental"},
            ]
        ),
        encoding="utf-8",
    )
    (data_dir / "official_operators.json").write_text(json.dumps([{"name": "rank"}]), encoding="utf-8")
    (data_dir / "official_datasets.json").write_text(
        json.dumps(
            [
                {"id": "analyst4", "name": "Analyst", "field_count": 2, "category": {"id": "analyst"}},
                {"id": "fundamental6", "name": "Fundamental", "field_count": 1, "category": {"id": "fundamental"}},
            ]
        ),
        encoding="utf-8",
    )

    loader = OfficialDataLoader()
    loader.load_all(data_dir)
    mapper = FieldDatasetMapper().build(loader)

    assert [field.id for field in loader.get_fields("analyst4")] == ["eps_revision", "sales_revision"]
    assert loader.validate_field("eps_revision", "analyst4") is True
    assert loader.validate_field("debt_ratio", "analyst4") is False
    assert mapper.fields_for("analyst4") == ["eps_revision", "sales_revision"]
    assert mapper.datasets_for("eps_revision") == ["analyst4"]


def test_official_loader_repairs_packaged_context_from_meipass(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    bundled_data = tmp_path / "bundle" / "data"
    bundled_data.mkdir(parents=True)
    (bundled_data / "official_fields.json").write_text(
        json.dumps([{"id": "close", "dataset": {"id": "pv1", "name": "Price Volume"}}]),
        encoding="utf-8",
    )
    (bundled_data / "official_operators.json").write_text(
        json.dumps([{"name": "rank"}]),
        encoding="utf-8",
    )
    (bundled_data / "official_datasets.json").write_text(
        json.dumps([{"id": "pv1", "name": "Price Volume", "field_count": 1}]),
        encoding="utf-8",
    )
    (bundled_data / "official_fields.meta.json").write_text('{"source":"official_api"}', encoding="utf-8")

    monkeypatch.setattr("brain_alpha_ops.data.loader.runtime_project_root", lambda: runtime_root)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path / "bundle"), raising=False)

    loader = OfficialDataLoader()
    loader.load_all("data")

    target_data = runtime_root / "data"
    assert (target_data / "official_fields.json").is_file()
    assert (target_data / "official_operators.json").is_file()
    assert (target_data / "official_datasets.json").is_file()
    assert (target_data / "official_fields.meta.json").is_file()
    assert loader.field_count == 1
    assert loader.operator_count == 1
    assert loader.dataset_count == 1
    assert loader.validate_field("close") is True
    assert loader.validate_operator("rank") is True
    assert loader.get_dataset("pv1") is not None


def test_packaged_context_repair_does_not_overwrite_valid_runtime_files(monkeypatch, tmp_path):
    runtime_data = tmp_path / "runtime" / "data"
    bundled_data = tmp_path / "bundle" / "data"
    runtime_data.mkdir(parents=True)
    bundled_data.mkdir(parents=True)
    (runtime_data / "official_fields.json").write_text(
        json.dumps([{"id": "runtime_close"}]),
        encoding="utf-8",
    )
    (bundled_data / "official_fields.json").write_text(
        json.dumps([{"id": "bundled_close"}]),
        encoding="utf-8",
    )
    (bundled_data / "official_operators.json").write_text(
        json.dumps([{"name": "rank"}]),
        encoding="utf-8",
    )
    (bundled_data / "official_datasets.json").write_text(
        json.dumps([{"id": "pv1", "name": "Price Volume", "field_count": 1}]),
        encoding="utf-8",
    )

    monkeypatch.setattr("sys._MEIPASS", str(tmp_path / "bundle"), raising=False)

    result = ensure_official_context_files(runtime_data)

    copied = result["copied"]
    assert isinstance(copied, list)
    assert "official_fields.json" not in copied
    assert "official_operators.json" in copied
    assert "official_datasets.json" in copied
    assert json.loads((runtime_data / "official_fields.json").read_text(encoding="utf-8")) == [
        {"id": "runtime_close"}
    ]


def test_packaged_context_file_manifest_covers_metadata_and_status():
    assert PACKAGED_OFFICIAL_CONTEXT_FILES == (
        "official_fields.json",
        "official_operators.json",
        "official_datasets.json",
        "official_fields.meta.json",
        "official_operators.meta.json",
        "official_datasets.meta.json",
        "official_context_refresh_status.json",
    )


def test_official_loader_preserves_existing_cache_when_refresh_target_is_empty(tmp_path):
    source = tmp_path / "source"
    empty = tmp_path / "empty"
    source.mkdir()
    empty.mkdir()
    (source / "official_fields.json").write_text(json.dumps([{"name": "close"}]), encoding="utf-8")

    loader = OfficialDataLoader()
    loader.load_all(source)

    result = loader.refresh(empty, max_retries=1)

    assert result["status"] == "refresh_failed"
    assert loader.field_count == 1
    assert loader.validate_field("close") is True
