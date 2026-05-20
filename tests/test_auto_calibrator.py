import json

from brain_alpha_ops.research.auto_calibrator import AutoCalibrator


def _write_alpha_features(path, count):
    rows = [
        {
            "alpha_id": f"a{i}",
            "pass_fail": "PASS",
            "sharpe": 1.0 + i / 100.0,
            "fitness": 0.8,
            "field_set": ["close"],
            "operator_set": ["rank"],
            "expression": "rank(close)",
            "family": "Momentum",
        }
        for i in range(count)
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_auto_calibrator_counts_all_pass_records_for_trigger(tmp_path):
    _write_alpha_features(tmp_path / "alpha_features.jsonl", 4)
    calibrator = AutoCalibrator(str(tmp_path))
    calibrator.MIN_CALIBRATION_SAMPLES = 4
    calibrator.CALIBRATION_HISTORY_LIMIT = 2

    assert calibrator.needs_calibration() is True
    assert calibrator._count_passing_records() == 4
    assert len(calibrator._load_passing_records(limit=2)) == 2


def test_auto_calibrator_insufficient_report_includes_total_pass_records(tmp_path):
    _write_alpha_features(tmp_path / "alpha_features.jsonl", 2)
    calibrator = AutoCalibrator(str(tmp_path))
    calibrator.MIN_CALIBRATION_SAMPLES = 3
    calibrator.CALIBRATION_HISTORY_LIMIT = 1

    report = calibrator.calibrate()

    assert report["calibrated"] is False
    assert report["sample_size"] == 1
    assert report["total_pass_records"] == 2
    assert report["deficit"] == 1
