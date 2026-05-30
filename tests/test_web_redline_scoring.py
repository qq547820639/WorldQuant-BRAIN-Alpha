from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops import web_redline_scoring


def test_scoring_attribution_resolves_candidate_from_alpha_id(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
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
    assert payload["attribution_summary"]["visualization"]["node_count"] >= 1
    assert payload["hard_gates"][0]["gate_name"] == "BRAIN_HARD_GATES"
    assert "improvement_hints" in payload


def test_scoring_attribution_reports_missing_candidate(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web_redline_scoring, "load_run_config", lambda: config)

    payload = web_redline_scoring.handle_scoring_attribution({"alpha_id": "missing"})

    assert payload["ok"] is False
    assert payload["error_code"] == "SCORING_CANDIDATE_NOT_FOUND"


def test_scoring_evaluate_logs_score_history_append_failure(monkeypatch, tmp_path, caplog):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    candidate = Candidate(
        alpha_id="alpha_history_warning",
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
    )

    class FailingScoreHistoryDB:
        def __init__(self, _storage_dir):
            pass

        def append(self, _result):
            raise OSError("history store unavailable")

    monkeypatch.setattr(web_redline_scoring, "load_run_config", lambda: config)
    monkeypatch.setattr(web_redline_scoring, "ScoreHistoryDB", FailingScoreHistoryDB)
    caplog.set_level("WARNING", logger=web_redline_scoring.__name__)

    payload = web_redline_scoring.handle_scoring_evaluate({"candidate": candidate.to_dict()})

    assert payload["alpha_id"] == "alpha_history_warning"
    assert "score history append failed for alpha_id=alpha_history_warning" in caplog.text
    assert "history store unavailable" in caplog.text


def test_scoring_health_reports_auto_calibration_status(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
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


def test_checkpoint_status_uses_configured_storage_for_resume_and_history(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "run_1.checkpoint.json").write_text(
        '{"run_id":"run_1","phase_completed":"redline","candidates_generated":2,'
        '"simulations_completed":1,"submissions_made":0,"cycle_number":1,'
        '"timestamp":"2026-05-22T00:00:00+00:00","snapshot":{}}',
        encoding="utf-8",
    )
    history_dir = tmp_path / "run_history"
    history_dir.mkdir()
    (history_dir / "run_1.json").write_text(
        '{"run_id":"run_1","started_at":"2026-05-22T00:00:00+00:00",'
        '"completed_at":"2026-05-22T00:01:00+00:00","status":"completed",'
        '"phases":[{"status":"completed"}],"summary":{"total_candidates":2,"auto_submitted":0,"best_score":75}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(web_redline_scoring, "load_run_config", lambda: config)

    payload = web_redline_scoring.handle_checkpoint_status({})

    assert payload["ok"] is True
    assert payload["storage_dir"] == str(tmp_path)
    assert payload["resume_available"] is True
    assert payload["latest"]["phase_completed"] == "redline"
    assert payload["history_count"] == 1
    assert payload["latest_history"]["run_id"] == "run_1"
    assert payload["history_analytics"]["schema_version"] == "run_history_analytics.v1"
    assert payload["history_analytics"]["latest"]["best_score"] == 75
