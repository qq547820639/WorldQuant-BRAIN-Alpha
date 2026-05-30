from __future__ import annotations

import json
from types import SimpleNamespace

from brain_alpha_ops.research.auto_calibrator import AutoCalibrator
from brain_alpha_ops.research.scoring_params import ScoringParams


def _write_records(tmp_path, count: int) -> None:
    path = tmp_path / "alpha_features.jsonl"
    records = []
    for index in range(count):
        records.append({
            "pass_fail": "PASS",
            "field_set": ["close", "adv20"] if index % 2 == 0 else ["roe"],
            "operator_set": ["rank", "ts_rank", "winsorize"] if index % 2 == 0 else ["group_rank"],
            "expression": "rank(ts_rank(close, 20))" if index % 2 == 0 else "group_rank(roe, industry)",
            "hypothesis": "momentum quality signal with liquidity risk control",
            "family": "Liquidity" if index % 3 == 0 else "Value",
            "sharpe": 1.1 + (index % 5) * 0.1,
            "prior_score": 70 + index % 10,
            "empirical_score": 60 + index % 20,
            "checklist_score": 80,
            "total_score": 72 + index % 12,
        })
    records.append({"pass_fail": "FAIL", "expression": "rank(open)", "sharpe": -0.2})
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_auto_calibrator_reports_insufficient_samples_and_apply_defaults(tmp_path):
    _write_records(tmp_path, 3)
    calibrator = AutoCalibrator(str(tmp_path))

    assert calibrator.needs_calibration() is False
    report = calibrator.calibrate()
    assert report["calibrated"] is False
    assert report["status"] == "insufficient_samples"
    assert report["deficit"] == calibrator.MIN_CALIBRATION_SAMPLES - 3

    scoring_config = SimpleNamespace()
    applied = calibrator.apply(scoring_config)
    assert applied is scoring_config
    assert scoring_config.prior_layer_weight == ScoringParams.defaults().layer_weights["prior"]
    assert scoring_config.prior_weights_override


def test_auto_calibrator_calibrates_and_persists_with_stubbed_weight_reports(tmp_path):
    _write_records(tmp_path, AutoCalibrator.MIN_CALIBRATION_SAMPLES)
    calibrator = AutoCalibrator(str(tmp_path))
    calibrator._calibrate_dimension_weights = lambda records: {
        "r_squared": 0.42,
        "optimized_weights": {"structure": 0.2, "field_operator_support": 0.3},
    }
    calibrator._calibrate_layer_weights = lambda records: {
        "optimized_weights": {"prior": 0.25, "empirical": 0.55, "checklist": 0.20},
    }

    assert calibrator.needs_calibration() is True
    report = calibrator.calibrate()

    assert report["calibrated"] is True
    assert report["total_pass_records"] == AutoCalibrator.MIN_CALIBRATION_SAMPLES
    assert report["calibration_quality"]["r_squared"] == 0.42
    assert report["layer_weights"]["optimized_weights"]["empirical"] == 0.55
    assert (tmp_path / "scoring_calibration.json").is_file()

    reloaded = AutoCalibrator(str(tmp_path))
    assert reloaded.needs_calibration() is False
    assert reloaded.params.layer_weights["prior"] == 0.25


def test_auto_calibrator_prior_scoring_branches_and_grid_helpers(tmp_path):
    calibrator = AutoCalibrator(str(tmp_path))
    params = ScoringParams.defaults()
    record = {
        "field_set": ["close", "adv20"],
        "operator_set": ["rank", "ts_delta", "winsorize"],
        "expression": "rank(ts_delta(close, 20))",
        "hypothesis": "momentum value quality liquidity risk management cross section",
        "family": "Hybrid",
        "sharpe": 1.4,
    }

    scores = {
        name: calibrator._compute_prior_for_record(record, dim, name)
        for name, dim in params.dimensions.items()
    }
    assert scores["structure"] > 0
    assert scores["field_operator_support"] >= params.dimensions["field_operator_support"].floor
    assert scores["data_compliance"] == params.dimensions["data_compliance"].high_score
    assert scores["risk_control_proxy"] == params.dimensions["risk_control_proxy"].tier_3_score
    assert scores["diversity"] == params.dimensions["diversity"].high_score
    assert scores["economic_logic"] >= 78

    empty_record = {"field_set": [], "operator_set": [], "expression": "", "hypothesis": "short", "sharpe": 0}
    assert calibrator._compute_prior_for_record(empty_record, params.dimensions["data_compliance"], "data_compliance") == params.dimensions["data_compliance"].low_score
    assert calibrator._compute_prior_for_record(empty_record, params.dimensions["horizon_turnover_proxy"], "horizon_turnover_proxy") == params.dimensions["horizon_turnover_proxy"].score_no_data
    assert calibrator._compute_prior_for_record(empty_record, params.dimensions["economic_logic"], "economic_logic") == params.dimensions["economic_logic"].fallback_insufficient_score
    assert calibrator._compute_prior_for_record(record, params.dimensions["structure"], "unknown") == 50.0

    combos = AutoCalibrator._generate_grid_combinations({"a": [1, 2], "b": [3, 4]})
    assert combos == [(1, 3), (1, 4), (2, 3), (2, 4)]
    assert AutoCalibrator._generate_grid_combinations({}) == [()]
    best_dim, best_mae = calibrator._grid_search_dimension(
        "structure",
        params.dimensions["structure"],
        {"base_score": [80.0, 90.0]},
        [record, empty_record],
    )
    assert best_dim.name == "structure"
    assert best_mae >= 0
    assert calibrator._compute_overall_mae(params, [record, empty_record]) >= 0
