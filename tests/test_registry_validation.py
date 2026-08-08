"""Tests for BRAIN capability registry consistency validation."""

import pytest

from brain_alpha_ops.registry_validation import (
    compare_threshold_snapshots,
    snapshot_threshold_version,
    validate_registry_consistency,
)


def _sample_registry() -> dict:
    return {
        "settings_options": {
            "sector": ["Technology", "Financials"],
            "market": ["US", "CN"],
            "dataset": ["dataset:cn_cash_flow", "dataset:cn_income"],
        },
        "parameters": {
            "operator": {
                "kind": "enum",
                "allowed": ["rank", "ts_delta", "ts_mean"],
            },
        },
        "official_context": {
            "files": {
                "alpha_dataset.json": {"id": "ds1"},
            },
        },
    }


def test_validate_registry_consistency_ok_when_consistent():
    result = validate_registry_consistency(
        registry=_sample_registry(),
        scoring_operators={"rank", "ts_delta"},
        gate_operators={"ts_mean"},
        generator_template_fields={"technology", "financials", "us", "cn"},
        config_dataset_ids={"dataset:cn_cash_flow"},
        thresholds={"slavg": 0.5},
    )
    assert result["ok"] is True
    assert result["blocking_count"] == 0
    assert result["schema_version"] == "registry_validation.v1"
    assert result["summary"]["registry_fields_count"] == 6
    assert result["summary"]["registry_operators_count"] == 3
    assert result["summary"]["registry_datasets_count"] == 3
    assert result["threshold_snapshot"]["threshold_count"] == 1


def test_validate_registry_consistency_flags_missing_template_fields():
    result = validate_registry_consistency(
        registry=_sample_registry(),
        generator_template_fields={"technology", "nonexistent_field"},
    )
    assert result["ok"] is False
    assert result["blocking_count"] == 1
    assert result["findings"][0]["code"] == "template_field_not_in_registry"
    assert "nonexistent_field" in result["findings"][0]["details"]["missing_fields"]


def test_validate_registry_consistency_flags_missing_operators():
    result = validate_registry_consistency(
        registry=_sample_registry(),
        scoring_operators={"rank", "unknown_op"},
        gate_operators={"unknown_gate_op"},
    )
    assert result["ok"] is False
    codes = [f["code"] for f in result["findings"]]
    assert "operator_not_in_registry" in codes
    assert "scoring_operator_not_in_registry" in codes
    assert "gate_operator_not_in_registry" in codes


def test_validate_registry_consistency_flags_missing_datasets():
    result = validate_registry_consistency(
        registry=_sample_registry(),
        config_dataset_ids={"dataset:cn_cash_flow", "dataset:not_present"},
    )
    assert result["ok"] is False
    assert result["findings"][0]["code"] == "config_dataset_not_in_registry"
    assert "dataset:not_present" in result["findings"][0]["details"]["missing_datasets"]


def test_validate_registry_consistency_uses_default_registry():
    result = validate_registry_consistency()
    # Default registry loads from the bundled capability registry or {}.
    assert result["schema_version"] == "registry_validation.v1"
    assert "checked_at" in result


def test_snapshot_threshold_version_hashes_content():
    a = snapshot_threshold_version({"x": 1}, version_label="v1", description="first")
    b = snapshot_threshold_version({"x": 2}, version_label="v1", description="second")
    assert a["version_label"] == "v1"
    assert a["description"] == "first"
    assert a["threshold_count"] == 1
    assert a["content_hash"] != b["content_hash"]
    assert len(a["content_hash"]) == 16


def test_compare_threshold_snapshots_detects_changes():
    a = snapshot_threshold_version({"x": 1, "y": 2})
    b = snapshot_threshold_version({"x": 1, "z": 3})
    diff = compare_threshold_snapshots(a, b)
    assert diff["identical"] is False
    assert diff["removed"] == ["y"]
    assert diff["added"] == ["z"]


def test_compare_threshold_snapshots_identical():
    a = snapshot_threshold_version({"x": 1})
    b = snapshot_threshold_version({"x": 1})
    diff = compare_threshold_snapshots(a, b)
    assert diff["identical"] is True
    assert diff["changed"] == []