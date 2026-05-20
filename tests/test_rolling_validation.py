from brain_alpha_ops.research.rolling_validation import RollingValidationService


def test_rolling_validation_passes_stable_windows_and_attaches_submission():
    candidate = {
        "alpha_id": "stable",
        "expression": "rank(ts_delta(close, 20))",
        "official_metrics": {"rolling_fitness": [1.0, 1.1, 1.05, 0.9, 0.85, 0.8, 0.75, 0.7]},
        "submission": {},
    }

    report = RollingValidationService().evaluate(candidate, windows=4)

    assert report["ok"] is True
    assert report["schema_version"] == "rolling_validation_report.v1"
    assert report["passed"] is True
    assert report["status"] == "pass"
    assert len(report["windows"]) == 4
    assert candidate["submission"]["rolling_validation_report"] == report


def test_rolling_validation_flags_obvious_decay():
    report = RollingValidationService().evaluate(
        {
            "alpha_id": "decay",
            "expression": "rank(close)",
            "official_metrics": {"fitness_series": [1.0, 0.8, 0.4, 0.2, 0.05, -0.1, -0.2, -0.3]},
            "submission": {},
        },
        windows=4,
    )

    assert report["passed"] is False
    assert report["status"] == "fail"
    assert report["decay_ratio"] < 0.5


def test_rolling_validation_reports_insufficient_data():
    report = RollingValidationService().evaluate(
        {
            "alpha_id": "thin",
            "expression": "rank(close)",
            "official_metrics": {"rolling_sharpe": [0.5, 0.4, 0.3]},
            "submission": {},
        }
    )

    assert report["status"] == "insufficient_data"
    assert report["passed"] is False
    assert report["sample_size"] == 3
