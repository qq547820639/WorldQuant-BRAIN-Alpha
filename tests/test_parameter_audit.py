from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot


def test_parameter_audit_snapshot_covers_trace_sections_and_canonical_thresholds():
    config = RunConfig(environment="production")

    snapshot = build_parameter_audit_snapshot(config, auto_submit=False, source="test")

    assert snapshot["ok"] is True
    assert snapshot["schema_version"] == "parameter_audit_snapshot.v1"
    assert snapshot["thresholds_zero_deviation"] is True
    assert snapshot["api_paths_aligned"] is True
    assert snapshot["sections"]["ops.settings"]["type"] == "REGULAR"
    assert snapshot["canonical_thresholds"]["min_sharpe"]["canonical"] == 1.25
    assert set(snapshot["traceable_sections"]) == {
        "ops.settings",
        "ops.budget",
        "ops.thresholds",
        "ops.submission_policy",
        "ops.scoring",
        "ops.official_api",
    }
    assert snapshot["config_hash"]


def test_parameter_audit_snapshot_flags_threshold_drift():
    config = RunConfig(environment="production")
    config.ops.thresholds.min_sharpe = 1.20

    snapshot = build_parameter_audit_snapshot(config)

    assert snapshot["ok"] is False
    assert snapshot["blocking_count"] == 1
    assert snapshot["canonical_thresholds"]["min_sharpe"]["match"] is False
    assert snapshot["findings"][0]["code"] == "threshold_drift"
