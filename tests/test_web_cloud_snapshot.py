from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from brain_alpha_ops.web_cloud_snapshot import (
    cloud_alpha_snapshot,
    datasets_from_fields,
    official_context_file_counts,
    read_storage_jsonl_stats,
    save_official_context_json,
)


def _config(storage, cache, *, context_cache_ttl_seconds=3600):
    return SimpleNamespace(
        ops=SimpleNamespace(
            storage_dir=str(storage),
            official_api=SimpleNamespace(cache_dir=str(cache), context_cache_ttl_seconds=context_cache_ttl_seconds),
        )
    )


def test_cloud_alpha_snapshot_reads_storage_dedupes_and_counts_context(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = lambda: _config(storage, cache)
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
    load_config = lambda: _config(storage, cache)
    (cache / "user_alphas_recent.json").write_text(
        json.dumps({"results": [{"id": "cloud_1", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS"}}]}),
        encoding="utf-8",
    )

    snapshot = cloud_alpha_snapshot(load_config=load_config, runtime_root=lambda: tmp_path)

    assert snapshot["summary"]["source"] == "api_cache"
    assert snapshot["summary"]["passed_unsubmitted_count"] == 1
    assert snapshot["alphas"][0]["id"] == "cloud_1"


def test_datasets_from_fields_aggregates_dataset_references(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = lambda: _config(storage, cache)

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
    load_config = lambda: _config(storage, cache)
    (storage / "checks.jsonl").write_text('{"alpha_id":"a1"}\nnot-json\n', encoding="utf-8")

    stats = read_storage_jsonl_stats("checks.jsonl", limit=10, load_config=load_config)

    assert stats["parsed_count"] == 1
    assert stats["skipped_invalid_count"] == 1


def test_official_context_manifest_marks_missing_and_expired_files(tmp_path):
    storage = tmp_path / "storage"
    cache = tmp_path / "cache"
    storage.mkdir()
    cache.mkdir()
    load_config = lambda: _config(storage, cache)
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
