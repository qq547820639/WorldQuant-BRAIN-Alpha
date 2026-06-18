from __future__ import annotations

from pathlib import Path

from brain_alpha_ops.web_cloud.snapshot import save_official_context_json
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.expression_official_context import (
    expression_delta,
    expression_official_context_proof,
)


def _write_context(tmp_path: Path) -> RunConfig:
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    save_official_context_json(
        "official_fields.json",
        [
            {"name": "close", "category": "pv"},
            {"name": "returns", "category": "pv"},
            {"name": "eps_revision", "category": "analyst"},
        ],
        load_config=lambda: config,
    )
    save_official_context_json(
        "official_operators.json",
        [{"name": "rank"}, {"name": "ts_rank"}, {"name": "winsorize"}, {"name": "group_neutralize"}],
        load_config=lambda: config,
    )
    save_official_context_json(
        "official_datasets.json",
        [
            {"id": "pv1", "name": "Price Volume", "field_count": 2, "category": {"id": "pv"}},
            {"id": "analyst4", "name": "Analyst", "field_count": 1, "category": {"id": "analyst"}},
        ],
        load_config=lambda: config,
    )
    return config


def test_expression_official_context_proof_accepts_official_expression(tmp_path):
    _write_context(tmp_path)

    proof = expression_official_context_proof("rank(ts_rank(close, 30))", dataset_id="pv1", data_dir=str(tmp_path))

    assert proof["schema_version"] == "expression-official-context-proof.v1"
    assert proof["official_api_called"] is False
    assert proof["passed"] is True
    assert proof["expression"]["fields"] == ["close"]
    assert proof["expression"]["operators"] == ["rank", "ts_rank"]
    assert proof["official_context"]["blocking_count"] == 0


def test_expression_official_context_proof_blocks_unknown_field_and_operator(tmp_path):
    _write_context(tmp_path)

    proof = expression_official_context_proof("rank(ts_fake(custom_field, 20))", dataset_id="pv1", data_dir=str(tmp_path))

    assert proof["passed"] is False
    assert "missing_official_fields" in proof["reasons"]
    assert "missing_official_operators" in proof["reasons"]
    assert proof["missing_fields"] == ["custom_field"]
    assert proof["missing_operators"] == ["ts_fake"]


def test_expression_official_context_proof_blocks_active_dataset_mismatch(tmp_path):
    _write_context(tmp_path)

    proof = expression_official_context_proof("rank(eps_revision)", dataset_id="pv1", data_dir=str(tmp_path))

    assert proof["passed"] is False
    assert "active_dataset_field_mismatch" in proof["reasons"]
    assert proof["missing_fields"] == []
    assert proof["dataset_mismatches"] == ["eps_revision"]


def test_expression_official_context_proof_accepts_group_context_fields(tmp_path):
    _write_context(tmp_path)

    proof = expression_official_context_proof("group_neutralize(rank(close), subindustry)", dataset_id="pv1", data_dir=str(tmp_path))

    assert proof["passed"] is True
    assert proof["group_context_fields"] == ["subindustry"]
    assert proof["missing_fields"] == []


def test_expression_delta_reports_parser_derived_changes():
    delta = expression_delta("rank(ts_rank(close, 30))", "rank(close)")

    assert delta["schema_version"] == "expression-delta.v1"
    assert delta["changed"] is True
    assert delta["fields_unchanged"] == ["close"]
    assert delta["operators_added"] == ["ts_rank"]
    assert delta["operators_unchanged"] == ["rank"]
    assert delta["windows_added"] == [30]
