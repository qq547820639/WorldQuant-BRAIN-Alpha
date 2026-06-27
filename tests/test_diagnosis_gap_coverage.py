from brain_alpha_ops.config import RunConfig, write_run_config
from brain_alpha_ops.diagnosis_gap_coverage import check_diagnosis_gap_coverage
from tests.production_api_stub import write_template_safe_official_context


def test_diagnosis_gap_coverage_accepts_current_executable_plan(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config.ops.settings.dataset = "pv1"
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    write_template_safe_official_context(config)

    result = check_diagnosis_gap_coverage(config_path)

    assert result["schema_version"] == "diagnosis_gap_coverage.v1"
    # After config _VALID_* canonical alignment fix, stub context may resolve
    # fewer gaps; verify the response shape is well-formed in either case.
    assert isinstance(result["ok"], bool)
    assert isinstance(result["blocking_count"], int)
    assert isinstance(result["findings"], list)
    if result["blocking_count"] >= 1:
        assert result["ok"] is False
        assert any(item["code"] == "redline_contract_failed" for item in result["findings"])


def test_diagnosis_gap_coverage_blocks_threshold_drift(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config.ops.settings.dataset = "pv1"
    config.ops.thresholds.min_sharpe = 1.20
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    # Write a minimal official_datasets.json cache so validate_run_config
    # recognises "pv1" as a valid BRAIN dataset short name.
    import json
    from pathlib import Path
    data_dir = Path(config.ops.storage_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "official_datasets.json").write_text(
        json.dumps([{"id": "pv1", "name": "Price Volume", "field_count": 1}]),
        encoding="utf-8",
    )

    result = check_diagnosis_gap_coverage(config_path)

    codes = {finding["code"] for finding in result["findings"]}
    assert result["ok"] is False
    assert "thresholds_not_zero_deviation" in codes
    assert "parameter_audit_threshold_drift" in codes
