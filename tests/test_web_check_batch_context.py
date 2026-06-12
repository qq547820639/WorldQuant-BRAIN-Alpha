from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops import web
from brain_alpha_ops.web_check_batch_context import check_batch_official_context_payload
from brain_alpha_ops.web_cloud_snapshot import save_official_context_json


def _write_context(tmp_path: Path) -> RunConfig:
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    config.ops.settings.dataset = "pv1"
    save_official_context_json(
        "official_fields.json",
        [{"name": "close", "category": "pv"}, {"name": "returns", "category": "pv"}],
        load_config=lambda: config,
    )
    save_official_context_json(
        "official_operators.json",
        [{"name": "rank"}, {"name": "ts_rank"}],
        load_config=lambda: config,
    )
    save_official_context_json(
        "official_datasets.json",
        [{"id": "pv1", "name": "Price Volume", "field_count": 2, "category": {"id": "pv"}}],
        load_config=lambda: config,
    )
    return config


def test_check_batch_official_context_payload_uses_parser_proof(tmp_path):
    config = _write_context(tmp_path)

    result = check_batch_official_context_payload(
        {
            "expressions": ["rank(close)", "rank(custom_field)"],
            "data_fields": ["custom_field"],
            "operators": ["ts_fake"],
        },
        load_run_config=lambda: config,
    )

    assert result["ok"] is True
    assert result["checked"] == 2
    assert result["valid_count"] == 1
    assert result["invalid_count"] == 1
    assert result["results"][0]["status"] == "OFFICIAL_CONTEXT_PASSED"
    failed = result["results"][1]
    assert failed["status"] == "OFFICIAL_CONTEXT_FAILED"
    assert failed["official_context_proof"]["official_api_called"] is False
    assert result["results"][0]["official_context_proof"]["expression"]["fields"] == ["close"]
    assert result["results"][0]["official_context_proof"]["expression"]["operators"] == ["rank"]
    assert failed["official_context_proof"]["missing_fields"] == ["custom_field"]


def test_check_batch_official_context_payload_accepts_single_expression_string(tmp_path):
    config = _write_context(tmp_path)

    result = check_batch_official_context_payload(
        {"expressions": "rank(ts_rank(close, 20))"},
        load_run_config=lambda: config,
    )

    assert result["ok"] is True
    assert result["checked"] == 1
    assert result["valid_count"] == 1
    assert result["results"][0]["official_context_proof"]["expression"]["operators"] == ["rank", "ts_rank"]


def test_check_batch_official_context_payload_rejects_malformed_expression_list():
    result = check_batch_official_context_payload({"expressions": {"bad": "shape"}})

    assert result == {"ok": False, "error": "expressions must be a list of strings"}


def test_real_check_batch_keeps_storage_dir_when_config_has_no_dataset_settings(tmp_path, monkeypatch):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    save_official_context_json(
        "official_fields.json",
        [{"name": "unique_af016_field", "category": "pv"}],
        load_config=lambda: config,
    )
    save_official_context_json(
        "official_operators.json",
        [{"name": "rank"}],
        load_config=lambda: config,
    )
    save_official_context_json(
        "official_datasets.json",
        [{"id": "pv1", "name": "Price Volume", "field_count": 1, "category": {"id": "pv"}}],
        load_config=lambda: config,
    )
    monkeypatch.setattr(web, "load_run_config", lambda: SimpleNamespace(ops=SimpleNamespace(storage_dir=str(tmp_path))))

    result = web._real_check_batch({"expressions": ["rank(unique_af016_field)"], "dataset_id": "pv1"})

    assert result["ok"] is True
    assert result["valid_count"] == 1
    proof = result["results"][0]["official_context_proof"]
    assert proof["official_api_called"] is False
    assert proof["expression"]["fields"] == ["unique_af016_field"]
