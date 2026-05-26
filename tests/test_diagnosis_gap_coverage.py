from brain_alpha_ops.config import RunConfig, write_run_config
from brain_alpha_ops.diagnosis_gap_coverage import check_diagnosis_gap_coverage
from brain_alpha_ops.web_cloud_snapshot import save_official_context_json


def test_diagnosis_gap_coverage_accepts_current_executable_plan(tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    save_official_context_json("official_fields.json", [{"name": "close"}, {"name": "volume"}], load_config=lambda: config)
    save_official_context_json("official_operators.json", [{"name": "rank"}], load_config=lambda: config)
    save_official_context_json(
        "official_datasets.json",
        [{"id": "pv1", "name": "Price Volume", "field_count": 2}],
        load_config=lambda: config,
    )

    result = check_diagnosis_gap_coverage(config_path)

    assert result["ok"] is True
    assert result["schema_version"] == "diagnosis_gap_coverage.v1"
    assert result["blocking_count"] == 0
    assert result["coverage"]["parameter_audit"] == "parameter_audit_snapshot.v1"


def test_diagnosis_gap_coverage_blocks_threshold_drift(tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path / "data")
    config.ops.thresholds.min_sharpe = 1.20
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)

    result = check_diagnosis_gap_coverage(config_path)

    codes = {finding["code"] for finding in result["findings"]}
    assert result["ok"] is False
    assert "thresholds_not_zero_deviation" in codes
    assert "parameter_audit_threshold_drift" in codes
