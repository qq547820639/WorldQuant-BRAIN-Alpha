from datetime import datetime, timedelta, timezone
import json

from brain_alpha_ops.data.official_context_validation import validate_official_context
from brain_alpha_ops.web_cloud_snapshot import save_official_context_json


class _Config:
    class _Ops:
        storage_dir = ""

        class _OfficialAPI:
            context_cache_ttl_seconds = 3600

        official_api = _OfficialAPI()

    ops = _Ops()


def _load_config(storage):
    config = _Config()
    config.ops.storage_dir = str(storage)
    return lambda: config


def _write_context(storage):
    load_config = _load_config(storage)
    save_official_context_json(
        "official_fields.json",
        [{"name": "close"}, {"name": "volume"}],
        load_config=load_config,
    )
    save_official_context_json(
        "official_operators.json",
        [{"name": "rank"}],
        load_config=load_config,
    )
    save_official_context_json(
        "official_datasets.json",
        [{"id": "pv1", "name": "Price Volume", "field_count": 2}],
        load_config=load_config,
    )


def test_official_context_validation_accepts_complete_lineage(tmp_path):
    storage = tmp_path / "data"
    _write_context(storage)

    result = validate_official_context(data_dir=storage)

    assert result["ok"] is True
    assert result["blocking_ok"] is True
    assert result["p1_count"] == 0
    assert result["lineage"]["field_count_sum_matches"] is True


def test_official_context_validation_flags_stale_metadata_as_p1(tmp_path):
    storage = tmp_path / "data"
    _write_context(storage)
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    for path in storage.glob("*.meta.json"):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata["expires_at"] = expired
        path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    result = validate_official_context(data_dir=storage)

    assert result["ok"] is False
    assert result["blocking_ok"] is True
    assert result["p1_count"] == 3
    assert {item["code"] for item in result["findings"]} == {"metadata_stale"}


def test_official_context_validation_blocks_dataset_field_count_drift(tmp_path):
    storage = tmp_path / "data"
    _write_context(storage)
    datasets_path = storage / "official_datasets.json"
    datasets = json.loads(datasets_path.read_text(encoding="utf-8"))
    datasets[0]["field_count"] = 1
    datasets_path.write_text(json.dumps(datasets, ensure_ascii=False), encoding="utf-8")

    result = validate_official_context(data_dir=storage)

    assert result["blocking_ok"] is False
    assert any(item["code"] == "dataset_field_count_mismatch" for item in result["findings"])
