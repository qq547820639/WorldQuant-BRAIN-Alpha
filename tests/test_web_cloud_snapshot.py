from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

from brain_alpha_ops.runtime_constants import CloudDefaults
from brain_alpha_ops.web_cloud.snapshot import (
    cached_user_alpha_paths,
    cloud_alpha_cache_probe,
    cloud_alpha_snapshot,
    datasets_from_fields,
    latest_cached_user_alphas,
    official_context_file_counts,
    read_storage_jsonl_stats,
    refresh_cloud_context_for_check_service,
    save_official_context_json,
)


def _config(storage, cache, *, context_cache_ttl_seconds=3600):
    return SimpleNamespace(
        ops=SimpleNamespace(
            storage_dir=str(storage),
            official_api=SimpleNamespace(cache_dir=str(cache), context_cache_ttl_seconds=context_cache_ttl_seconds),
        )
    )


def _loader(storage, cache, *, context_cache_ttl_seconds=3600):
    def load_config():
        return _config(storage, cache, context_cache_ttl_seconds=context_cache_ttl_seconds)

    return load_config


def test_cloud_alpha_snapshot_reads_storage_dedupes_and_counts_context(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    save_official_context_json("official_fields.json", [{"id": "close"}], load_config=load_config, runtime_root=lambda: tmp_path)
    save_official_context_json("official_operators.json", [{"name": "rank"}], load_config=load_config, runtime_root=lambda: tmp_path)
    save_official_context_json("official_datasets.json", [{"id": "fundamental6"}], load_config=load_config, runtime_root=lambda: tmp_path)
    rows = [
        {"id": "a1", "status": "UNSUBMITTED", "metrics": {"pass_fail": "FAIL"}, "updated_at": "2026-01-01T00:00:00Z"},
        {"id": "mock_1", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS"}, "updated_at": "2026-01-02T00:00:00Z"},
        {"id": "a1", "status": "ACTIVE", "metrics": {"pass_fail": "PASS"}, "updated_at": "2026-01-03T00:00:00Z"},
    ]
    (storage / "cloud_alphas.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    snapshot = cloud_alpha_snapshot(load_config=load_config, runtime_root=lambda: tmp_path)

    assert [row["id"] for row in snapshot["alphas"]] == ["a1"]
    assert snapshot["summary"]["source"] == "storage"
    assert snapshot["summary"]["submitted_count"] == 1
    assert snapshot["summary"]["fields_count"] == 1
    assert snapshot["summary"]["operators_count"] == 1
    assert snapshot["summary"]["datasets_count"] == 1
    assert snapshot["summary"]["context_cache_manifest"]["schema_version"] == "official_context_cache_manifest.v1"
    assert snapshot["summary"]["context_cache_manifest"]["complete"] is True
    assert snapshot["summary"]["context_cache_manifest"]["is_stale"] is False
    assert snapshot["summary"]["context_cache_manifest"]["record_count_total"] == 3
    assert snapshot["summary"]["context_cache_manifest"]["sha256"]
    assert snapshot["summary"]["context_cache_metadata"]["official_fields.json"]["is_stale"] is False
    assert snapshot["summary"]["context_cache_metadata"]["official_fields.json"]["age_seconds"] >= 0


def test_cloud_alpha_snapshot_falls_back_to_latest_api_cache(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    (cache / "user_alphas_recent.json").write_text(
        json.dumps({"results": [{"id": "cloud_1", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS"}}]}),
        encoding="utf-8",
    )

    snapshot = cloud_alpha_snapshot(load_config=load_config, runtime_root=lambda: tmp_path)

    assert snapshot["summary"]["source"] == "api_cache"
    assert snapshot["summary"]["passed_unsubmitted_count"] == 1
    assert snapshot["alphas"][0]["id"] == "cloud_1"


def test_cloud_alpha_cache_probe_reads_storage_without_full_count(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    rows = [{"id": "prod_alpha", "status": "ACTIVE"}]
    rows.extend({"id": f"mock_{index}", "status": "UNSUBMITTED"} for index in range(700))
    (storage / "cloud_alphas.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    probe = cloud_alpha_cache_probe(load_config=load_config, stale_seconds=999999)

    assert probe["ok"] is True
    assert probe["source"] == "storage"
    assert "count" not in probe
    assert "total" not in probe
    assert probe["loaded_at"]
    assert probe["is_stale"] is False


def test_cloud_alpha_cache_probe_falls_back_to_api_cache_when_storage_has_no_production_rows(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    (storage / "cloud_alphas.jsonl").write_text('{"id":"mock_1"}\n', encoding="utf-8")
    (cache / "user_alphas_recent.json").write_text(
        json.dumps({"results": [{"id": "cloud_1", "status": "UNSUBMITTED"}]}),
        encoding="utf-8",
    )

    probe = cloud_alpha_cache_probe(load_config=load_config, stale_seconds=999999)

    assert probe["ok"] is True
    assert probe["source"] == "api_cache"
    assert probe["count"] == 1
    assert probe["total"] == 1


def test_cloud_alpha_snapshot_default_reads_full_cloud_cache(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    rows = [{"id": f"a{index}", "updated_at": f"2026-01-01T00:00:{index % 60:02d}Z"} for index in range(10005)]
    (storage / "cloud_alphas.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    snapshot = cloud_alpha_snapshot(load_config=load_config, runtime_root=lambda: tmp_path)

    assert len(snapshot["alphas"]) == 10005
    assert {row["id"] for row in snapshot["alphas"]} >= {"a0", "a10004"}


def test_cloud_alpha_snapshot_limit_only_bounds_returned_rows_not_total(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    rows = [{"id": f"a{index}", "updated_at": f"2026-01-01T00:00:{index % 60:02d}Z"} for index in range(12)]
    (storage / "cloud_alphas.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    snapshot = cloud_alpha_snapshot(limit=5, load_config=load_config, runtime_root=lambda: tmp_path)

    assert len(snapshot["alphas"]) == 5
    assert snapshot["summary"]["count"] == 12
    assert snapshot["summary"]["total"] == 12
    assert snapshot["summary"]["returned_count"] == 5
    assert snapshot["summary"]["display_limit"] == 5


def test_cached_user_alpha_paths_are_bounded_to_recent_files(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    for index in range(5):
        path = cache / f"user_alphas_{index}.json"
        path.write_text("[]", encoding="utf-8")
        path.touch()

    paths = cached_user_alpha_paths(load_config=load_config, max_files=3)

    assert len(paths) == 3
    assert all(path.name.startswith("user_alphas_") for path in paths)


def test_cached_user_alpha_paths_defaults_to_all_cache_files(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    for index in range(5):
        path = cache / f"user_alphas_{index}.json"
        path.write_text("[]", encoding="utf-8")
        path.touch()

    paths = cached_user_alpha_paths(load_config=load_config)

    assert len(paths) == 5
    assert {path.name for path in paths} == {f"user_alphas_{index}.json" for index in range(5)}


def test_cached_user_alpha_paths_warns_when_cache_dir_unreadable(monkeypatch, tmp_path, caplog):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    original_glob = Path.glob

    def fail_glob(self, pattern):
        if self == cache:
            raise OSError("permission denied")
        return original_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", fail_glob)

    with caplog.at_level(logging.WARNING):
        paths = cached_user_alpha_paths(load_config=load_config, max_files=3)

    assert paths == []
    assert "failed to list cached user alpha files from" in caplog.text


def test_latest_cached_user_alphas_warns_and_skips_bad_cache_files(tmp_path, caplog):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    bad = cache / "user_alphas_bad.json"
    good = cache / "user_alphas_good.json"
    bad.write_text("{not-json", encoding="utf-8")
    good.write_text(json.dumps({"results": [{"id": "cloud_1"}]}), encoding="utf-8")
    os.utime(good, (1, 1))
    os.utime(bad, (2, 2))

    with caplog.at_level(logging.WARNING):
        rows = latest_cached_user_alphas(load_config=load_config, max_files=3)

    assert rows == [{"id": "cloud_1"}]
    assert "failed to read cached user alpha file" in caplog.text
    assert str(bad) in caplog.text


def test_save_official_context_json_warns_when_config_resolution_fails(tmp_path, caplog):
    def fail_load_config():
        raise RuntimeError("config unavailable")

    with caplog.at_level(logging.WARNING):
        save_official_context_json(
            "official_fields.json",
            [{"id": "close"}],
            load_config=fail_load_config,
            runtime_root=lambda: tmp_path,
        )

    target = tmp_path / CloudDefaults.OFFICIAL_CONTEXT_DATA_DIR / "official_fields.json"
    metadata = tmp_path / CloudDefaults.OFFICIAL_CONTEXT_DATA_DIR / "official_fields.meta.json"
    assert target.exists()
    assert metadata.exists()
    assert "failed to resolve configured storage dir while saving official context" in caplog.text
    assert "config unavailable" in caplog.text


def test_datasets_from_fields_aggregates_dataset_references(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)

    datasets = datasets_from_fields(
        [
            {"id": "close", "dataset": {"id": "fundamental6", "name": "Fundamental 6"}},
            {"id": "volume", "dataset_id": "fundamental6"},
            {"id": "sentiment", "dataset": {"id": "news", "name": "News"}},
        ],
        load_config=load_config,
        runtime_root=lambda: tmp_path,
    )

    assert [row["id"] for row in datasets] == ["fundamental6", "news"]
    assert datasets[0]["field_count"] == 2
    assert datasets[0]["name"] == "Fundamental 6"


def test_read_storage_jsonl_stats_uses_configured_storage(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    (storage / "checks.jsonl").write_text('{"alpha_id":"a1"}\nnot-json\n', encoding="utf-8")

    stats = read_storage_jsonl_stats("checks.jsonl", limit=10, load_config=load_config)

    assert stats["parsed_count"] == 1
    assert stats["skipped_invalid_count"] == 1


def test_refresh_cloud_context_progress_uses_reference_count_not_cloud_total():
    class Store:
        def __init__(self):
            self.updates = []

        def update(self, job_id, **kwargs):
            self.updates.append((job_id, kwargs))

    class API:
        def list_user_alphas(self, _sync_range, *, force_refresh=False, progress_callback=None):
            assert force_refresh is True
            if progress_callback:
                progress_callback({
                    "scanned": 10_800,
                    "total": 10_000,
                    "api_reported_total": 10_000,
                    "filter_window_count": 10_000,
                    "page_size": 100,
                    "page_limit": 100,
                    "pages_fetched": 108,
                    "expected_pages": 100,
                    "next_offset": 10_800,
                })
            return [{"id": "alpha_live"}]

        def list_fields(self, *_args):
            return [{"id": "close", "dataset": {"id": "pv1"}}]

        def list_operators(self, *_args):
            return [{"name": "rank"}]

        def list_datasets(self, *_args):
            return [{"id": "pv1"}]

    class Repo:
        def __init__(self):
            self.merged = []

        def merge_cloud_alphas(self, rows, *, sync_range):
            self.merged.append((rows, sync_range))

    store = Store()
    repo = Repo()

    rows, error = refresh_cloud_context_for_check_service(
        API(),
        repo,
        "all",
        "job_cloud_reference",
        3,
        "quick",
        region="USA",
        refresh_remote=True,
        store=store,
        official_context_file_counts=lambda: {"fields_count": 1, "operators_count": 1, "datasets_count": 1},
        datasets_from_fields=lambda fields: [{"id": "pv1", "field_count": len(fields)}],
        persist_official_context=lambda *_args: None,
        safe_error_message=str,
    )

    cloud_progress = next(
        update["progress"]
        for _job_id, update in store.updates
        if update["progress"]["status_code"] == "CHECK_CLOUD_SYNC"
    )
    saved_progress = next(
        update["progress"]
        for _job_id, update in store.updates
        if update["progress"]["status_code"] == "CHECK_CLOUD_SYNC_SAVED"
    )
    assert rows == [{"id": "alpha_live"}]
    assert error == ""
    assert "接口分页参考数 10000 条，不是云端 Alpha 总量" in cloud_progress["message"]
    assert "接口窗口" not in cloud_progress["message"]
    assert cloud_progress["cloud_scanned"] == 10_800
    assert cloud_progress["cloud_api_reported_total"] == 10_000
    assert cloud_progress["cloud_filter_window_count"] == 10_000
    assert "cloud_total" not in cloud_progress
    assert saved_progress["cloud_saved_count"] == 1
    assert "本地已保存 1 条云端 Alpha" in saved_progress["message"]
    assert "cloud_total" not in saved_progress


def test_official_context_manifest_marks_missing_and_expired_files(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    save_official_context_json("official_fields.json", [{"id": "close"}], load_config=load_config, runtime_root=lambda: tmp_path)
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    metadata_path = storage / "official_fields.meta.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["expires_at"] = expired_at.isoformat()
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    counts = official_context_file_counts(load_config=load_config, runtime_root=lambda: tmp_path)

    manifest = counts["context_cache_manifest"]
    assert manifest["schema_version"] == "official_context_cache_manifest.v1"
    assert manifest["is_stale"] is True
    assert manifest["complete"] is False
    assert "official_fields.json" in manifest["stale_files"]
    assert "official_operators.json" in manifest["missing_files"]
    assert "official_datasets.json" in manifest["missing_files"]
    assert manifest["record_counts"]["official_fields.json"] == 1
    assert counts["context_cache_metadata"]["official_fields.json"]["is_expired"] is True
    assert counts["context_cache_metadata"]["official_fields.json"]["expires_in_seconds"] <= 0


def test_official_context_manifest_rejects_metadata_that_no_longer_matches_file(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = _loader(storage, cache)
    save_official_context_json("official_fields.json", [{"id": "close"}], load_config=load_config, runtime_root=lambda: tmp_path)
    save_official_context_json("official_operators.json", [{"name": "rank"}], load_config=load_config, runtime_root=lambda: tmp_path)
    save_official_context_json("official_datasets.json", [{"id": "fundamental6"}], load_config=load_config, runtime_root=lambda: tmp_path)
    (storage / "official_fields.json").write_text(
        json.dumps([{"id": "close"}, {"id": "volume"}]),
        encoding="utf-8",
    )

    counts = official_context_file_counts(load_config=load_config, runtime_root=lambda: tmp_path)

    manifest = counts["context_cache_manifest"]
    field_meta = counts["context_cache_metadata"]["official_fields.json"]
    assert counts["fields_count"] == 2
    assert field_meta["metadata_record_count"] == 1
    assert field_meta["record_count"] == 2
    assert field_meta["integrity_ok"] is False
    assert set(field_meta["integrity_errors"]) == {"record_count_mismatch", "sha256_mismatch"}
    assert manifest["complete"] is False
    assert manifest["is_stale"] is True
    assert manifest["invalid_files"] == ["official_fields.json"]
