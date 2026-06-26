import json
import logging

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.scoring import official_scoring as official_scoring_module
from brain_alpha_ops.scoring.gates import GateConfig
from brain_alpha_ops.scoring.history import ScoreHistoryDB
from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem


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
    payload = result.to_dict()
    assert payload["settings_trace"]["delay"] == 1
    assert payload["settings_trace"]["type"] == "REGULAR"
    assert payload["threshold_trace"]["min_sharpe"]["source"] == "BRAIN_Official"
    assert payload["calibration"]["purpose"].startswith("Track whether local priors")
    assert payload["attribution_summary"]["visualization"]["node_count"] >= 1
    assert set(simulated["checks"]) >= {
        "sharpe",
        "fitness",
        "turnover_min",
        "turnover_platform",
        "self_correlation",
        "weight_concentration",
        "sub_universe_sharpe",
    }


def test_official_scoring_does_not_reconstruct_pass_without_official_pass_fail():
    metrics = {
        "sharpe": 1.5,
        "fitness": 1.1,
        "turnover": 0.2,
        "returns": 0.08,
        "drawdown": 0.05,
        "correlation": 0.2,
        "weight_concentration": 0.05,
        "sub_universe_sharpe": 1.3,
        "margin": 5.5,
    }

    result = OfficialScoringSystem().evaluate(_candidate(metrics))
    simulated = result.simulated_api_output

    assert simulated["status"] == "UNKNOWN"
    assert simulated["gate"]["hard_gate_passed"] is False
    assert simulated["gate"]["submission_ready"] is False
    assert simulated["gate"]["reconstructed_hard_gate_passed"] is True
    assert simulated["meta"]["official_pass_fail_source"] == "missing_official_pass_fail"
    assert result.api_output_deviation == 1.0
    assert any("official pass_fail missing" in item for item in result.deviation_details)


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


def test_official_scoring_hard_gates_include_zero_point_items_and_survive_sparse_rows():
    scoring = OfficialScoringSystem()
    scorecard = {
        "empirical": {
            "items": [
                {
                    "name": "mandatory_zero_weight",
                    "is_hard_gate": True,
                    "points": 0,
                    "passed": False,
                    "actual": 0.5,
                    "target": 1.0,
                    "direction": ">=",
                },
                {"is_hard_gate": True, "points": 0},
                {
                    "name": "soft_zero_weight",
                    "is_hard_gate": False,
                    "points": 0,
                    "passed": False,
                    "actual": 0.1,
                    "target": 0.2,
                    "direction": ">=",
                },
            ]
        }
    }

    hard_gate = scoring._build_hard_gates(_candidate({}), scorecard)[0]
    soft_gate = scoring._build_soft_gates(_candidate({}), scorecard)[0]

    assert hard_gate.passed is False
    assert [item["name"] for item in hard_gate.check_items] == ["mandatory_zero_weight", "-"]
    assert "mandatory_zero_weight" in hard_gate.failed_items[0]
    assert [item["name"] for item in soft_gate.check_items] == ["soft_zero_weight"]


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
    assert gate.gate_name == "OFFICIAL_CONFIGURED_GATE"
    assert gate.threshold_source == "BRAIN_Official"
    assert gate.check_items[0]["source"] == "BRAIN_Official"
    assert gate.check_items[0]["zero_deviation"] is True

    history_path = tmp_path / "score_history.jsonl"
    db = ScoreHistoryDB(str(history_path))
    db.append(result)
    db.append(result)
    db.append(result)

    assert len(history_path.read_text(encoding="utf-8").splitlines()) == 3
    assert json.loads(history_path.read_text(encoding="utf-8").splitlines()[0])["alpha_id"] == "score_alpha"
    assert db.convergence_stats()["status"] == "ready"


def test_official_scoring_in_memory_history_is_bounded(monkeypatch):
    monkeypatch.setattr(official_scoring_module, "_MAX_SCORE_HISTORY_PER_ALPHA", 3)
    monkeypatch.setattr(official_scoring_module, "_MAX_SCORE_HISTORY_TOTAL_ENTRIES", 5)
    scoring = OfficialScoringSystem()
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

    for _index in range(6):
        scoring.evaluate(_candidate(metrics))

    assert len(scoring._score_history["score_alpha"]) == 3
    assert scoring.get_score_trend("score_alpha") == "stable"

    for index in range(6):
        candidate = _candidate(metrics)
        candidate.alpha_id = f"score_alpha_{index}"
        scoring.evaluate(candidate)

    total_entries = sum(len(history) for history in scoring._score_history.values())
    assert total_entries <= 5


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


def test_gate_config_rejects_non_official_hard_gate():
    scoring = OfficialScoringSystem()

    try:
        GateConfig(scoring.thresholds).add_hard_gate(
            "drawdown",
            lambda metrics, thresholds: metrics["drawdown"] <= thresholds.max_drawdown,
        )
    except ValueError as exc:
        assert "not a BRAIN official hard check" in str(exc)
    else:
        raise AssertionError("GateConfig accepted a non-official hard gate")


def test_gate_config_flags_configured_hard_gate_deviation():
    scoring = OfficialScoringSystem()
    gate = (
        GateConfig(scoring.thresholds)
        .add_hard_gate("sharpe", lambda _metrics, _thresholds: False)
        .evaluate({"sharpe": 1.8, "fitness": 1.2, "turnover": 0.2})
    )

    assert gate.passed is False
    assert gate.check_items[0]["official_passed"] is True
    assert gate.check_items[0]["configured_passed"] is False
    assert gate.check_items[0]["zero_deviation"] is False
    assert "deviates from BRAIN official check" in gate.failed_items[0]


def test_gate_config_warns_when_configured_check_raises(caplog):
    scoring = OfficialScoringSystem()

    def broken_check(_metrics, _thresholds):
        raise RuntimeError("gate backend unavailable")

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.scoring.gates"):
        gate = GateConfig(scoring.thresholds).add_hard_gate("sharpe", broken_check).evaluate(
            {"sharpe": 1.8, "fitness": 1.2, "turnover": 0.2}
        )

    assert gate.passed is False
    assert gate.check_items[0]["configured_passed"] is False
    assert gate.check_items[0]["error"] == "gate backend unavailable"
    assert "configured gate check failed: gate=sharpe" in caplog.text
    assert "gate backend unavailable" in caplog.text
