from __future__ import annotations

import pytest

cw = pytest.importorskip("calibrate_weights", reason="calibrate_weights standalone module not installed")

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import prior_score


class _ScoreHistoryDBNotReady:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir

    def convergence_stats(self):
        return {"status": "warming_up", "total_evaluations": 0}


class _ScoreHistoryDBStalled:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir

    def convergence_stats(self):
        return {
            "status": "ready",
            "total_evaluations": 20,
            "trend": "declining",
            "recent_avg": 1.0,
            "avg_score": 2.0,
            "pass_rate": 0.5,
        }


def test_compute_prior_dimensions_matches_runtime_prior_score_defaults():
    record = {
        "expression": "rank(ts_delta(close, 20)) + winsorize(volume)",
        "field_set": ["close", "volume", "adv20"],
        "operator_set": ["rank", "ts_delta", "winsorize"],
        "hypothesis": "price momentum with liquidity and risk management confirmation",
        "family": "Liquidity",
    }
    candidate = Candidate(
        alpha_id="alpha_shared_prior",
        expression=record["expression"],
        family=record["family"],
        hypothesis=record["hypothesis"],
        data_fields=list(record["field_set"]),
        operators=list(record["operator_set"]),
    )
    runtime_dims = dict(prior_score(candidate)["dimensions"])
    runtime_dims.pop("economic_concepts", None)

    assert cw.compute_prior_dimensions(record) == runtime_dims


def test_auto_calibrate_if_stalled_returns_not_triggered_when_not_ready(monkeypatch):
    monkeypatch.setattr("brain_alpha_ops.scoring.history.ScoreHistoryDB", _ScoreHistoryDBNotReady)

    result = cw.auto_calibrate_if_stalled("data")

    assert result["ok"] is True
    assert result["triggered"] is False
    assert result["reason"] == "insufficient_data"
    assert result["stats"]["status"] == "warming_up"


def test_auto_calibrate_if_stalled_reports_calibration_failure_when_features_are_insufficient(monkeypatch):
    monkeypatch.setattr("brain_alpha_ops.scoring.history.ScoreHistoryDB", _ScoreHistoryDBStalled)
    monkeypatch.setattr(cw, "load_alpha_features", lambda path: [{"row": index} for index in range(7)])

    result = cw.auto_calibrate_if_stalled("data")

    assert result["ok"] is True
    assert result["triggered"] is True
    assert result["calibration_failed"] is True
    assert result["reason"] == "insufficient features for calibration"
    assert result["stats"]["trend"] == "declining"


def test_auto_calibrate_if_stalled_merges_advice_when_stalled(monkeypatch):
    monkeypatch.setattr("brain_alpha_ops.scoring.history.ScoreHistoryDB", _ScoreHistoryDBStalled)
    monkeypatch.setattr(cw, "load_alpha_features", lambda path: [{"row": index} for index in range(8)])
    monkeypatch.setattr(
        cw,
        "calibrate_prior_weights",
        lambda records, target_metric="sharpe": {
            "optimized_weights": {"structure": 0.41},
            "optimized_layer_weights": {"unused": 0.0},
        },
    )
    monkeypatch.setattr(
        cw,
        "calibrate_scorecard_weights",
        lambda records: {"optimized_layer_weights": {"prior_layer_weight": 0.33}},
    )

    result = cw.auto_calibrate_if_stalled("data")

    assert result["ok"] is True
    assert result["triggered"] is True
    assert result["reason"].startswith("score convergence stalled")
    assert result["prior_calibration"]["optimized_weights"] == {"structure": 0.41}
    assert result["scorecard_calibration"]["optimized_layer_weights"] == {"prior_layer_weight": 0.33}
    assert result["advice"] == {"prior_weights_override": {"structure": 0.41}, "prior_layer_weight": 0.33}
