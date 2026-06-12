from __future__ import annotations

from brain_alpha_ops.brain_api.canonical import CANONICAL_SETTINGS
from brain_alpha_ops.web_capability_registry import (
    REGISTRY_SCHEMA_VERSION,
    build_capability_registry,
    capability_settings_options,
    check_capability_registry,
)


def _schema() -> dict:
    return {
        "schema_version": "web_config_schema.test",
        "required_settings_fields": [
            "region",
            "universe",
            "delay",
            "neutralization",
            "instrumentType",
            "type",
            "decay",
            "truncation",
            "pasteurization",
            "nanHandling",
            "unitHandling",
            "language",
        ],
        "settings_options": capability_settings_options(
            [{"id": "pv1", "name": "Price Volume", "field_count": 12}]
        ),
        "dataset_options": [{"id": "pv1", "name": "Price Volume", "field_count": 12}],
    }


def _counts() -> dict:
    return {
        "fields_count": 12,
        "operators_count": 7,
        "datasets_count": 1,
        "context_cache_manifest": {
            "complete": True,
            "is_stale": False,
            "record_counts": {
                "official_fields.json": 12,
                "official_operators.json": 7,
                "official_datasets.json": 1,
            },
        },
    }


def test_capability_settings_options_come_from_canonical_settings():
    options = capability_settings_options()

    assert set(options["region"]) == CANONICAL_SETTINGS["region"]
    assert set(options["universe"]) == CANONICAL_SETTINGS["universe"]
    assert {int(value) for value in options["delay"]} == CANONICAL_SETTINGS["delay"]
    assert set(options["neutralization"]) == CANONICAL_SETTINGS["neutralization"]


def test_capability_registry_passes_with_complete_local_official_context():
    registry = build_capability_registry(public_config_schema=_schema, official_context_file_counts=_counts)

    assert registry["schema_version"] == REGISTRY_SCHEMA_VERSION
    assert registry["status"] == "ready"
    assert registry["human_confirmation_required"] is False
    assert registry["official_api_called"] is False
    assert registry["settings_options"]["dataset"] == ["pv1"]
    assert registry["parameters"]["decay"]["min"] == 0
    assert registry["parameters"]["truncation"]["max"] == 1.0
    assert registry["parameters"]["visualization"]["kind"] == "boolean"
    assert registry["official_context"]["files"]["official_fields.json"]["record_count"] == 12
    assert registry["blocking_count"] == 0


def test_capability_registry_needs_human_confirmation_for_empty_or_missing_context():
    registry = build_capability_registry(
        public_config_schema=_schema,
        official_context_file_counts=lambda: {
            "fields_count": 0,
            "operators_count": 0,
            "datasets_count": 0,
        },
    )

    assert registry["status"] == "needs_human_confirmation"
    assert registry["human_confirmation_required"] is True
    assert registry["blocking_count"] >= 4
    assert {finding["code"] for finding in registry["findings"]} >= {
        "official_context_manifest_missing",
        "official_fields_empty",
        "official_operators_empty",
        "official_datasets_empty",
    }


def test_capability_registry_detects_web_config_schema_drift():
    def drifted_schema() -> dict:
        schema = _schema()
        schema["settings_options"] = dict(schema["settings_options"])
        schema["settings_options"]["region"] = ["MARS"]
        return schema

    result = check_capability_registry(
        public_config_schema=drifted_schema,
        official_context_file_counts=_counts,
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "schema_setting_options_drift:region"
        for finding in result["findings"]
    )
