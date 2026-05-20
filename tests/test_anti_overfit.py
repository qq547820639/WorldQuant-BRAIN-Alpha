from brain_alpha_ops.research.anti_overfit import AntiOverfitService


def test_anti_overfit_passes_stable_candidate_and_attaches_submission():
    candidate = {
        "alpha_id": "a1",
        "expression": "rank(ts_delta(close, 20))",
        "official_metrics": {"ic_series": [0.04, 0.035, 0.03, 0.045] * 20},
        "submission": {},
    }

    report = AntiOverfitService().evaluate(candidate)

    assert report["ok"] is True
    assert report["schema_version"] == "anti_overfit_report.v1"
    assert report["recommendation"] in {"pass", "caution"}
    assert report["sample_size"] == 80
    assert candidate["submission"]["anti_overfit_report"] == report


def test_anti_overfit_blocks_insufficient_samples():
    report = AntiOverfitService().evaluate(
        {
            "alpha_id": "thin",
            "expression": "rank(close)",
            "official_metrics": {"ic_series": [0.02, 0.03]},
            "submission": {},
        }
    )

    assert report["recommendation"] == "block"
    assert report["passed_count"] == 0
    assert {item["details"]["reason"] for item in report["tests"]} == {"insufficient_samples"}


def test_anti_overfit_uses_synthetic_series_when_no_ic_history():
    report = AntiOverfitService().evaluate(
        {
            "alpha_id": "synthetic",
            "expression": "rank(ts_mean(volume, 5))",
            "official_metrics": {"rank_ic": 0.03, "sharpe": 1.5},
            "submission": {},
        }
    )

    assert report["ok"] is True
    assert report["sample_size"] == 60
    assert {item["name"] for item in report["tests"]} == {
        "ic_stability",
        "subsample_stress",
        "placebo",
        "half_life",
    }
