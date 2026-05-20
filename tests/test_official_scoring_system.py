import json

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.scoring.official_scoring import GateConfig, OfficialScoringSystem, ScoreHistoryDB


def _candidate(metrics):
    candidate = Candidate(
        alpha_id="score_alpha",
        expression="rank(ts_delta(close, 20) / ts_std(returns, 20)) + rank(ts_mean(volume / adv20, 20))",
        family="Hybrid",
        hypothesis="Risk-adjusted price momentum confirmed by liquidity participation across a medium horizon.",
        data_fields=["close", "returns", "volume", "adv20"],
        operators=["rank", "ts_delta", "ts_std", "ts_mean"],
        local_quality={"passed": True, "score": 84},
    )
    candidate.official_alpha_id = "official_score_alpha"
    candidate.official_metrics = metrics
    return candidate


def test_official_scoring_uses_official_pass_fail_for_api_simulation():
    result = OfficialScoringSystem().evaluate(
        _candidate(
            {
                "sharpe": 1.5,
                "fitness": 1.1,
                "turnover": 0.2,
                "returns": 0.08,
                "drawdown": 0.05,
                "correlation": 0.2,
                "weight_concentration": 0.05,
                "sub_universe_sharpe": 1.3,
                "margin": 5.5,
                "pass_fail": "PASS",
            }
        )
    )

    simulated = result.simulated_api_output

    assert simulated["status"] == "PASS"
    assert simulated["gate"]["submission_ready"] is True
    assert simulated["gate"]["reconstructed_hard_gate_passed"] is True
    assert result.api_output_deviation == 0.0
    assert set(simulated["checks"]) >= {
        "sharpe",
        "fitness",
        "turnover_min",
        "turnover_platform",
        "self_correlation",
        "weight_concentration",
        "sub_universe_sharpe",
    }


def test_official_scoring_reports_deviation_when_local_reconstruction_disagrees():
    result = OfficialScoringSystem().evaluate(
        _candidate(
            {
                "sharpe": 0.9,
                "fitness": 0.8,
                "turnover": 0.2,
                "returns": 0.05,
                "drawdown": 0.05,
                "correlation": 0.2,
                "weight_concentration": 0.05,
                "sub_universe_sharpe": 0.8,
                "margin": 5.5,
                "pass_fail": "PASS",
            }
        )
    )

    assert result.simulated_api_output["status"] == "PASS"
    assert result.simulated_api_output["gate"]["reconstructed_hard_gate_passed"] is False
    assert result.api_output_deviation == 1.0
    assert any("pass_fail mismatch" in item for item in result.deviation_details)


def test_gate_config_and_score_history_are_structured(tmp_path):
    scoring = OfficialScoringSystem()
    result = scoring.evaluate(
        _candidate(
            {
                "sharpe": 1.8,
                "fitness": 1.3,
                "turnover": 0.25,
                "returns": 0.09,
                "drawdown": 0.04,
                "correlation": 0.2,
                "weight_concentration": 0.04,
                "sub_universe_sharpe": 1.5,
                "margin": 6.0,
                "pass_fail": "PASS",
            }
        )
    )

    gate = (
        GateConfig(scoring.thresholds)
        .add_hard_gate("sharpe", lambda metrics, thresholds: metrics["sharpe"] >= thresholds.min_sharpe)
        .add_soft_gate("margin", lambda metrics, _thresholds: metrics["margin"] >= 4.0)
        .evaluate({"sharpe": 1.8, "margin": 6.0})
    )
    assert gate.passed is True
    assert gate.check_items[0]["source"] == "BRAIN_Official"

    history_path = tmp_path / "score_history.jsonl"
    db = ScoreHistoryDB(str(history_path))
    db.append(result)
    db.append(result)
    db.append(result)

    assert len(history_path.read_text(encoding="utf-8").splitlines()) == 3
    assert json.loads(history_path.read_text(encoding="utf-8").splitlines()[0])["alpha_id"] == "score_alpha"
    assert db.convergence_stats()["status"] == "ready"


def test_scoring_web_cli_compatibility_helpers(tmp_path):
    metrics = {
        "sharpe": 1.8,
        "fitness": 1.3,
        "turnover": 0.25,
        "returns": 0.09,
        "drawdown": 0.04,
        "correlation": 0.2,
        "weight_concentration": 0.04,
        "sub_universe_sharpe": 1.5,
        "margin": 6.0,
        "pass_fail": "PASS",
    }
    candidate_dict = _candidate(metrics).to_dict()
    gate_config = GateConfig.from_thresholds(OfficialScoringSystem().thresholds)
    result = OfficialScoringSystem(gate_config=gate_config).evaluate(candidate_dict)

    assert result.alpha_id == "score_alpha"
    assert result.simulated_api_output["status"] == "PASS"

    db = ScoreHistoryDB(str(tmp_path))
    db.append(result)
    assert (tmp_path / "score_history.jsonl").is_file()
