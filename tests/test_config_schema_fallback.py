from __future__ import annotations

import json

from brain_alpha_ops import config_schema


def test_config_schema_fallback_reports_required_type_enum_and_numeric_errors(monkeypatch, capsys):
    monkeypatch.setattr(config_schema, "jsonschema", None)

    errors = config_schema.validate_config_with_jsonschema(
        {
            "environment": "staging",
            "auto_submit": "yes",
            "credentials": [],
            "web": {"host": "", "port": 0},
            "ops": {
                "settings": {
                    "instrumentType": "EQUITY",
                    "region": "MARS",
                    "universe": "TOP3000",
                    "delay": 99,
                    "neutralization": "SUBINDUSTRY",
                    "language": "FASTEXPR",
                },
                "budget": {"max_candidates_per_cycle": 0},
                "scoring": {"local_quality_weight": "bad"},
                "thresholds": {"max_self_correlation": 2.0},
                "submission_policy": {},
                "official_api": {"base_url": ""},
                "storage_dir": "",
            },
        }
    )

    stderr = capsys.readouterr().err
    assert "jsonschema not installed" in stderr
    assert any("environment" in error and "staging" in error for error in errors)
    assert any("auto_submit" in error and "boolean" in error for error in errors)
    assert any("credentials" in error and "not an object" in error for error in errors)
    assert any("web.host" in error and "shorter" in error for error in errors)
    assert any("web.port" in error and "minimum" in error for error in errors)
    assert any("ops.settings.region" in error and "MARS" in error for error in errors)
    assert any("ops.settings.delay" in error and "99" in error for error in errors)
    assert any("ops.scoring.local_quality_weight" in error and "number" in error for error in errors)
    assert any("ops.thresholds.max_self_correlation" in error and "maximum" in error for error in errors)


def test_config_schema_fallback_enforces_required_roots_for_empty_config(monkeypatch):
    monkeypatch.setattr(config_schema, "jsonschema", None)

    errors = config_schema.validate_config_with_jsonschema({})

    assert any("missing required property 'environment'" in error for error in errors)
    assert any("missing required property 'ops'" in error for error in errors)


def test_config_schema_handles_schema_errors_and_file_read_errors(monkeypatch, tmp_path):
    class _BadValidator:
        def __init__(self, schema):
            raise config_schema.jsonschema.SchemaError("bad schema")

    monkeypatch.setattr(config_schema.jsonschema, "Draft202012Validator", _BadValidator)

    assert config_schema.validate_config_with_jsonschema({"environment": "production"})[0].startswith("schema error:")

    missing_path = tmp_path / "missing.json"
    is_valid, errors = config_schema.validate_config_file(missing_path)
    assert is_valid is False
    assert errors[0].startswith(f"File read error at {missing_path}:")


def test_validate_config_file_accepts_valid_partial_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"environment": "production"}), encoding="utf-8")

    is_valid, errors = config_schema.validate_config_file(config_path)

    assert is_valid is True
    assert errors == []
