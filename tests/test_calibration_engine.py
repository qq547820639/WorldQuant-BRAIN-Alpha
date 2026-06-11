from __future__ import annotations

import json

from brain_alpha_ops.research import calibration_engine as cal


def _pass_records(count: int = 16):
    records = []
    for i in range(count):
        sharpe = 1.3 + (i % 5) * 0.12
        records.append({
            "alpha_id": f"alpha_{i}",
            "expression": "rank(ts_delta(close, 20))",
            "field_set": ["close", "volume", "returns"],
            "operator_set": ["rank", "ts_delta"],
            "hypothesis": "Momentum signal with liquid fields",
            "family": "Momentum",
            "pass_fail": "PASS",
            "sharpe": sharpe,
            "fitness": 1.0 + i * 0.03,
            "margin": 4.0 + i,
        })
    return records


def test_load_alpha_features_skips_missing_and_bad_json(tmp_path):
    assert cal.load_alpha_features(str(tmp_path / "missing.jsonl")) == []
    path = tmp_path / "alpha_features.jsonl"
    path.write_text('{"alpha_id":"a1"}\nnot json\n{"alpha_id":"a2"}\n', encoding="utf-8")

    rows = cal.load_alpha_features(str(path))

    assert [row["alpha_id"] for row in rows] == ["a1", "a2"]


def test_calibrate_prior_weights_reports_insufficient_samples():
    result = cal.calibrate_prior_weights([{"pass_fail": "FAIL", "sharpe": 9.0}])

    assert result["sample_size"] == 0
    assert "insufficient samples" in result["error"]
    assert result["optimized_weights"] == {}


def test_calibrate_prior_weights_returns_normalized_weights():
    result = cal.calibrate_prior_weights(_pass_records(), target_metric="sharpe")

    assert result["sample_size"] == 16
    assert result["target"] == "sharpe"
    assert result["optimized_weights"]
    assert abs(sum(result["optimized_weights"].values()) - 1.0) < 0.01
    assert len(result["dimension_correlations"]) == 8
    assert "Top predictor" in result["summary"]


def test_calibrate_scorecard_weights_grid_searches_layers():
    result = cal.calibrate_scorecard_weights(_pass_records())

    assert result["sample_size"] == 16
    assert result["optimized_weights"].keys() == {"prior", "empirical", "checklist"}
    assert abs(sum(result["optimized_weights"].values()) - 1.0) < 0.01
    assert result["correlation_with_sharpe"] >= 0


def test_calibrate_scorecard_weights_reports_insufficient_samples():
    result = cal.calibrate_scorecard_weights(_pass_records(3))

    assert result == {"sample_size": 3, "error": "insufficient samples"}


def test_generate_mock_features_and_print_report(capsys):
    records = cal.generate_mock_features(12)
    prior = cal.calibrate_prior_weights(records)
    scorecard = cal.calibrate_scorecard_weights(records)

    cal.print_calibration_report(prior, scorecard)

    output = capsys.readouterr().out
    assert "评分权重校准报告" in output
    assert len(records) == 12
    assert all("alpha_id" in record for record in records)


def test_auto_calibrate_if_stalled_paths(monkeypatch, tmp_path):
    class FakeDB:
        def __init__(self, _storage_dir):
            pass

        def convergence_stats(self):
            return {
                "status": "ready",
                "total_evaluations": 20,
                "trend": "stable",
                "recent_avg": 70,
                "avg_score": 71,
                "pass_rate": 0.1,
            }

    monkeypatch.setattr("brain_alpha_ops.scoring.history.ScoreHistoryDB", FakeDB)
    features = tmp_path / "alpha_features.jsonl"
    features.write_text("\n".join(json.dumps(row) for row in _pass_records(16)), encoding="utf-8")

    result = cal.auto_calibrate_if_stalled(
        str(tmp_path),
        min_evaluations=12,
        stall_threshold=3,
        features_path=str(features),
    )

    assert result["ok"] is True
    assert result["triggered"] is True
    assert result["prior_calibration"]["optimized_weights"]
    assert "score convergence stalled" in result["reason"]


def test_auto_calibrate_if_stalled_non_trigger_paths(monkeypatch, tmp_path):
    class NotReadyDB:
        def __init__(self, _storage_dir):
            pass

        def convergence_stats(self):
            return {"status": "empty"}

    monkeypatch.setattr("brain_alpha_ops.scoring.history.ScoreHistoryDB", NotReadyDB)
    assert cal.auto_calibrate_if_stalled(str(tmp_path))["reason"] == "insufficient_data"

    class ImprovingDB(NotReadyDB):
        def convergence_stats(self):
            return {
                "status": "ready",
                "total_evaluations": 20,
                "trend": "improving",
                "recent_avg": 80,
                "avg_score": 70,
                "pass_rate": 0.5,
            }

    monkeypatch.setattr("brain_alpha_ops.scoring.history.ScoreHistoryDB", ImprovingDB)
    result = cal.auto_calibrate_if_stalled(str(tmp_path), min_evaluations=12)
    assert result["triggered"] is False
    assert "not stalled" in result["reason"]
