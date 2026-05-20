from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops import web_redline_scoring


def test_scoring_attribution_resolves_candidate_from_alpha_id(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    repo = ResearchRepository(str(tmp_path))
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="alpha_attr",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Recent price strength can persist after ranking.",
            data_fields=["close"],
            operators=["rank"],
            official_metrics={
                "pass_fail": "PASS",
                "sharpe": 1.6,
                "fitness": 1.2,
                "turnover": 0.2,
                "returns": 0.05,
                "drawdown": 0.04,
                "correlation": 0.2,
                "weight_concentration": 0.04,
                "sub_universe_sharpe": 1.3,
                "subUniverseSize": 1000,
                "alphaSize": 1000,
                "margin": 5.0,
            },
        ),
    )
    monkeypatch.setattr(web_redline_scoring, "load_run_config", lambda: config)

    payload = web_redline_scoring.handle_scoring_attribution({"alpha_id": "alpha_attr"})

    assert payload["ok"] is True
    assert payload["attribution"]["name"] == "total_score"
    assert payload["hard_gates"][0]["gate_name"] == "BRAIN_HARD_GATES"
    assert "improvement_hints" in payload


def test_scoring_attribution_reports_missing_candidate(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web_redline_scoring, "load_run_config", lambda: config)

    payload = web_redline_scoring.handle_scoring_attribution({"alpha_id": "missing"})

    assert payload["ok"] is False
    assert payload["error_code"] == "SCORING_CANDIDATE_NOT_FOUND"


def test_scoring_health_reports_auto_calibration_status(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    (tmp_path / "alpha_features.jsonl").write_text(
        "\n".join(
            [
                '{"alpha_id":"a1","pass_fail":"PASS","sharpe":1.2,"fitness":1.0,"field_set":["close"],"operator_set":["rank"],"expression":"rank(close)","family":"Momentum"}',
                '{"alpha_id":"a2","pass_fail":"PASS","sharpe":1.3,"fitness":1.0,"field_set":["volume"],"operator_set":["rank"],"expression":"rank(volume)","family":"Liquidity"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(web_redline_scoring, "load_run_config", lambda: config)

    payload = web_redline_scoring.handle_scoring_health({})

    assert payload["ok"] is True
    assert payload["auto_calibration"]["available"] is True
    assert payload["auto_calibration"]["total_pass_records"] == 2
    assert payload["auto_calibration"]["triggered"] is False
