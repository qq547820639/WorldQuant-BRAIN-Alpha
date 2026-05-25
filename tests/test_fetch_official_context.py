import json

import pytest

import fetch_official_context
from brain_alpha_ops.config import RunConfig, write_run_config
from brain_alpha_ops.data.loader import OfficialDataLoader


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


def _write_config(tmp_path):
    config = RunConfig(environment="production")
    config.credentials.token = "test-token"
    config.ops.storage_dir = str(tmp_path / "data")
    config.ops.official_api.cache_dir = str(tmp_path / "api_cache")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    return config_path


def test_refresh_official_context_writes_context_and_status(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", FakeOfficialBrainAPI)
    config_path = _write_config(tmp_path)
    status_path = tmp_path / "refresh_status.json"

    result = fetch_official_context.refresh_official_context(config_path, status_output=status_path)

    assert result["ok"] is True
    assert result["status"] == "refreshed"
    assert result["counts"] == {"fields": 1, "operators": 1, "datasets": 1}
    assert (tmp_path / "data" / "official_fields.json").is_file()
    assert (tmp_path / "data" / "official_operators.json").is_file()
    assert (tmp_path / "data" / "official_datasets.json").is_file()
    saved_status = json.loads(status_path.read_text(encoding="utf-8"))
    assert saved_status["ok"] is True
    assert "test-token" not in status_path.read_text(encoding="utf-8")


def test_refresh_official_context_no_write_fetches_without_context_files(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_official_context, "OfficialBrainAPI", FakeOfficialBrainAPI)
    config_path = _write_config(tmp_path)
    status_path = tmp_path / "refresh_status.json"

    result = fetch_official_context.refresh_official_context(config_path, write=False, status_output=status_path)

    assert result["ok"] is True
    assert result["status"] == "fetched_no_write"
    assert result["write_enabled"] is False
    assert not (tmp_path / "data" / "official_fields.json").exists()
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "fetched_no_write"


def test_refresh_official_context_records_missing_credentials(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    status_path = tmp_path / "refresh_status.json"
    write_run_config(config, config_path)

    result = fetch_official_context.refresh_official_context(config_path, status_output=status_path)

    assert result["ok"] is False
    assert result["error_code"] == "MISSING_CREDENTIALS"
    assert "environment variables" in result["error"]
    assert json.loads(status_path.read_text(encoding="utf-8"))["ok"] is False


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
