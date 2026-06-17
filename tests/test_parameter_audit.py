import json

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot
from scripts.check_parameter_traceability import run_parameter_audit


def test_parameter_audit_snapshot_covers_trace_sections_and_canonical_thresholds():
    config = RunConfig(environment="production")

    snapshot = build_parameter_audit_snapshot(config, auto_submit=False, source="test")

    assert snapshot["ok"] is True
    assert snapshot["schema_version"] == "parameter_audit_snapshot.v1"
    assert snapshot["thresholds_zero_deviation"] is True
    assert snapshot["api_paths_aligned"] is True
    assert snapshot["sections"]["ops.settings"]["type"] == "REGULAR"
    assert snapshot["canonical_thresholds"]["min_sharpe"]["canonical"] == 1.25
    assert snapshot["canonical_thresholds"]["max_prod_correlation"]["canonical"] == 0.70
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


def test_parameter_audit_snapshot_flags_prod_correlation_threshold_drift():
    config = RunConfig(environment="production")
    config.ops.thresholds.max_prod_correlation = 0.95

    snapshot = build_parameter_audit_snapshot(config)

    assert snapshot["ok"] is False
    assert snapshot["canonical_thresholds"]["max_prod_correlation"]["match"] is False
    assert any(
        finding["parameter"] == "max_prod_correlation"
        and finding["code"] == "threshold_drift"
        for finding in snapshot["findings"]
    )


def test_parameter_traceability_no_custom_extension_reports_mutation_scope(tmp_path):
    official_fields = [
        {"name": "close"},
        {"name": "returns"},
        {"name": "volume"},
        {"name": "adv20"},
        {"name": "adv60"},
        {"name": "open"},
        {"name": "high"},
        {"name": "low"},
        {"name": "vwap"},
        {"name": "cap"},
    ]
    official_operators = [
        {"name": name}
        for name in [
            "rank",
            "ts_delta",
            "ts_std_dev",
            "ts_rank",
            "zscore",
            "ts_mean",
            "ts_corr",
            "ts_decay_linear",
            "divide",
            "ts_covariance",
            "if_else",
            "greater",
            "winsorize",
            "ts_sum",
            "abs",
            "add",
            "divide",
            "group_backfill",
            "group_neutralize",
            "group_rank",
            "group_scale",
            "group_zscore",
            "inverse",
            "log",
            "max",
            "min",
            "multiply",
            "normalize",
            "reverse",
            "scale",
            "sign",
            "sqrt",
            "subtract",
            "ts_arg_max",
            "ts_arg_min",
            "ts_av_diff",
            "ts_backfill",
            "ts_delay",
            "ts_product",
            "ts_regression",
            "ts_zscore",
        ]
    ]
    (tmp_path / "official_fields.json").write_text(json.dumps(official_fields), encoding="utf-8")
    (tmp_path / "official_operators.json").write_text(json.dumps(official_operators), encoding="utf-8")
    (tmp_path / "official_datasets.json").write_text(json.dumps([{"id": "analyst4"}]), encoding="utf-8")

    result = run_parameter_audit(data_dir=str(tmp_path))

    check = result["checks"]["no_custom_extension_check"]
    assert check["coverage_scope"] == [
        "generator_fallback_templates",
        "evolution_mutation_engine",
        "legacy_mutate_expression",
    ]
    coverage_by_path = {item["path"]: item for item in check["coverage_paths"]}
    assert coverage_by_path["generator_fallback_templates"]["enforcement"] == "blocking"
    assert coverage_by_path["evolution_mutation_engine"]["checked"] is True
    assert coverage_by_path["legacy_mutate_expression"]["checked"] is True
    assert coverage_by_path["legacy_mutate_expression"]["details"]["operator_literals_checked"] > 0
    assert "generator/evolution/legacy mutation" in check["coverage_statement"]
    assert "fallback-only evidence is not reported as full coverage" in check["coverage_statement"]
