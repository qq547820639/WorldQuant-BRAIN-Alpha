from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate, PipelineEvent, PipelineResult
from brain_alpha_ops.ux import guided_pipeline
from brain_alpha_ops.ux.guided_pipeline import (
    CheckpointData,
    GuidedPipeline,
    PipelinePhase,
    RunRecord,
    classify_error,
    format_candidate_summary,
    format_error_for_user,
    format_pipeline_progress,
)


def _config(tmp_path, environment: str = "production") -> RunConfig:
    config = RunConfig(environment=environment)
    config.ops.storage_dir = str(tmp_path)
    return config


def _result(run_id: str = "run_cov") -> PipelineResult:
    candidate = Candidate(
        alpha_id="alpha_1",
        expression="rank(close)",
        family="price",
        hypothesis="coverage",
        scorecard={"total_score": 0.91, "decision_band": "submit_candidate"},
        gate={"submission_ready": False, "failed_reasons": ["low sharpe", "high turnover"]},
    )
    event = PipelineEvent(event="score_update", message="scored", alpha_id="alpha_1", level="SUCCESS")
    return PipelineResult(
        run_id=run_id,
        candidates=[candidate],
        events=[event],
        summary={
            "total_candidates": 1,
            "officially_simulated": 1,
            "auto_submitted": 0,
            "official_validation_attempted": 1,
            "official_validation_passed": 1,
            "submission_ready": 0,
            "score_distribution": {"submit_candidate": 1},
            "gate_summary": {"hard": {"pass": 0, "fail": 1}},
            "cycle": 2,
        },
    )


def test_guided_data_structures_and_error_fallback(monkeypatch, caplog):
    phase = PipelinePhase(name="init", description="Init")
    phase.start()
    phase.complete("ready")
    assert phase.to_dict()["status"] == "completed"

    failed = PipelinePhase(name="x", description="X")
    failed.fail("broken")
    assert failed.errors == ["broken"]

    checkpoint = CheckpointData.from_dict(
        {
            "run_id": "run_1",
            "phase_completed": "finalize",
            "candidates_generated": 1,
            "simulations_completed": 1,
            "submissions_made": 0,
            "cycle_number": 3,
            "ignored": "value",
        }
    )
    assert checkpoint.to_dict()["cycle_number"] == 3

    record = RunRecord(run_id="run_1", started_at="now", status="completed")
    assert record.to_dict()["status"] == "completed"

    monkeypatch.setattr(guided_pipeline, "_unified_classify", lambda _error: (_ for _ in ()).throw(RuntimeError("boom")))
    with caplog.at_level("WARNING", logger="brain_alpha_ops.ux.guided_pipeline"):
        info = classify_error(ValueError("bad value"))
    assert info == {
        "type": "ValueError",
        "message": "bad value",
        "fix": "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
        "retry": "maybe",
    }
    assert "guided pipeline error classification fallback failed" in caplog.text


def test_guided_pipeline_init_context_redline_and_stop_paths(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("BRAIN_USERNAME", raising=False)
    monkeypatch.delenv("BRAIN_PASSWORD", raising=False)
    monkeypatch.delenv("BRAIN_TOKEN", raising=False)

    pipeline = GuidedPipeline(_config(tmp_path))
    assert pipeline._should_stop() is False
    pipeline.stop()
    assert pipeline._should_stop() is True
    with caplog.at_level("WARNING", logger="brain_alpha_ops.ux.guided_pipeline"):
        assert GuidedPipeline(_config(tmp_path), stop_callback=lambda: (_ for _ in ()).throw(RuntimeError("stop")))._should_stop() is False
    assert "guided pipeline external stop callback failed; continuing execution" in caplog.text

    with pytest.raises(RuntimeError, match="生产环境需要"):
        pipeline._phase_init("run_missing_auth")

    monkeypatch.setenv("BRAIN_TOKEN", "token")
    authed = GuidedPipeline(_config(tmp_path))
    init_result = authed._phase_init("run_ok")
    assert init_result.run_id == "run_ok"
    assert authed.phases["init"].status == "completed"

    simulated = GuidedPipeline(_config(tmp_path, environment="local"))
    simulated._phase_init("run_local")
    assert "模拟模式" in simulated.phases["init"].result_summary

    from brain_alpha_ops.brain_api import context_defaults

    monkeypatch.setattr(context_defaults, "_ensure_loaded", lambda: None)
    monkeypatch.setitem(context_defaults._DEFAULTS_CACHE, "fields", [])
    monkeypatch.setitem(context_defaults._DEFAULTS_CACHE, "operators", [])
    authed._phase_context(init_result)
    assert authed.phases["context"].status == "failed"

    monkeypatch.setitem(context_defaults._DEFAULTS_CACHE, "fields", ["close"])
    monkeypatch.setitem(context_defaults._DEFAULTS_CACHE, "operators", ["rank"])
    authed._phase_context(init_result)
    assert authed.phases["context"].status == "completed"

    from brain_alpha_ops.compliance import redline_verifier

    class PassingVerifier:
        def __init__(self, run_config):
            self.run_config = run_config

        def verify_all(self):
            return SimpleNamespace(overall="PASS", passed=2, total_checks=2, violations=[])

    monkeypatch.setattr(redline_verifier, "RedLineVerifier", PassingVerifier)
    authed._phase_redline(init_result)
    assert authed.phases["redline"].status == "completed"

    blocking = SimpleNamespace(
        severity="BLOCKING",
        redline_id="RL-1",
        check_name="check",
        fix_guidance="fix it",
    )

    class FailingVerifier:
        def __init__(self, run_config):
            self.run_config = run_config

        def verify_all(self):
            return SimpleNamespace(overall="FAIL", passed=1, total_checks=2, violations=[blocking])

    failing_pipeline = GuidedPipeline(_config(tmp_path))
    monkeypatch.setattr(redline_verifier, "RedLineVerifier", FailingVerifier)
    with caplog.at_level("WARNING", logger="brain_alpha_ops.ux.guided_pipeline"):
        with pytest.raises(RuntimeError, match="TECH_REDLINE_BLOCKED"):
            failing_pipeline._phase_redline(init_result)
    assert "[RL-1]" in failing_pipeline.phases["redline"].warnings[0]
    assert "guided pipeline redline phase failed" in caplog.text


def test_guided_pipeline_core_events_failure_finalize_and_checkpoints(monkeypatch, tmp_path, caplog):
    pipeline = GuidedPipeline(_config(tmp_path))
    progress_events: list[tuple[str, str, dict]] = []
    pipeline.on_progress(lambda phase, status, data: progress_events.append((phase, status, data)))

    def fake_run_pipeline(run_config, *, progress_callback, stop_callback):
        progress_callback(PipelineEvent(event="score update", message="scored one", alpha_id="a1"))
        return _result()

    monkeypatch.setattr(guided_pipeline, "run_pipeline_from_config", fake_run_pipeline)
    result = pipeline._phase_core_pipeline(PipelineResult(run_id="run_cov", candidates=[], events=[], summary={}))
    assert ("scoring", "progress", {"event": "score update", "alpha_id": "a1", "message": "scored one"}) in progress_events
    assert GuidedPipeline._phase_id_from_core_progress("official backtest") == "simulation"
    assert GuidedPipeline._phase_id_from_core_progress("unknown") == "generation"

    monkeypatch.setattr(pipeline, "_save_run_record", lambda _result: (_ for _ in ()).throw(OSError("no disk")))
    with caplog.at_level("WARNING", logger="brain_alpha_ops.ux.guided_pipeline"):
        pipeline._phase_finalize(result)
    assert pipeline.phases["finalize"].status == "failed"
    assert "guided pipeline finalize phase failed" in caplog.text

    checkpoint_path = pipeline._save_checkpoint("run_cov", "finalize", result)
    assert checkpoint_path.endswith("run_cov.checkpoint.json")
    assert pipeline.load_checkpoint("missing") is None
    assert pipeline.load_checkpoint("run_cov").phase_completed == "finalize"

    corrupt = pipeline._checkpoint_dir / "zz_corrupt.checkpoint.json"
    corrupt.write_text("{", encoding="utf-8")
    with caplog.at_level("WARNING", logger="brain_alpha_ops.ux.guided_pipeline"):
        checkpoints = pipeline.list_checkpoints()
    assert checkpoints[0]["run_id"] == "run_cov"
    assert "guided pipeline checkpoint file skipped" in caplog.text
    assert pipeline.latest_checkpoint().run_id == "run_cov"
    assert GuidedPipeline._result_from_snapshot({}) is None
    with caplog.at_level("WARNING", logger="brain_alpha_ops.ux.guided_pipeline"):
        assert GuidedPipeline._result_from_snapshot({"run_id": "bad", "events": [{"event": "missing_message"}]}) is None
    assert "guided pipeline snapshot could not be restored" in caplog.text

    resumed = pipeline.resume("run_cov")
    assert resumed.run_id == "run_cov"

    empty_checkpoints = GuidedPipeline(_config(tmp_path / "empty"))
    assert empty_checkpoints.list_checkpoints() == []
    assert empty_checkpoints.latest_checkpoint() is None
    monkeypatch.setattr(empty_checkpoints, "run_guided", lambda: _result("alias_run"))
    assert empty_checkpoints.run().run_id == "alias_run"

    fallback = _result("fallback")
    monkeypatch.setattr(pipeline, "run_guided", lambda: fallback)
    assert pipeline.resume("missing").run_id == "fallback"

    def failing_run_pipeline(run_config, *, progress_callback, stop_callback):
        raise RuntimeError("core failed")

    failing = GuidedPipeline(_config(tmp_path))
    monkeypatch.setattr(guided_pipeline, "run_pipeline_from_config", failing_run_pipeline)
    with caplog.at_level("WARNING", logger="brain_alpha_ops.ux.guided_pipeline"):
        with pytest.raises(RuntimeError, match="core failed"):
            failing._phase_core_pipeline(PipelineResult(run_id="x", candidates=[], events=[], summary={}))
    assert failing.phases["generation"].status == "failed"
    assert "guided pipeline core pipeline phase failed" in caplog.text


def test_guided_pipeline_print_and_format_helpers(capsys, tmp_path):
    pipeline = GuidedPipeline(_config(tmp_path))
    pipeline.phases["init"].complete("done")
    pipeline.phases["context"].fail("empty context")
    pipeline.phases["redline"].start()

    pipeline.print_progress()
    pipeline.print_summary()
    pipeline.print_summary(_result())

    output = capsys.readouterr().out
    assert "Pipeline Progress" in output
    assert "No pipeline result is available yet" in output
    assert "Score Distribution" in output
    assert "Gate Results" in output

    candidate_text = format_candidate_summary(_result().candidates[0])
    assert "失败原因" in candidate_text
    assert "low sharpe" in candidate_text

    event_text = format_pipeline_progress(_result().events[0])
    assert "[+]" in event_text
    assert "score_update" in event_text

    error_text = format_error_for_user(RuntimeError("network timeout"))
    assert "错误类型" in error_text
    assert "修复建议" in error_text


def test_guided_pipeline_has_no_cli_adapter():
    assert not hasattr(guided_pipeline, "main")
