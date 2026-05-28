import json

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import PipelineResult
from brain_alpha_ops.ux import guided_pipeline
from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline


def test_guided_pipeline_completes_core_phases_and_uses_configured_storage(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    pipeline = GuidedPipeline(config)

    def fake_run_pipeline(run_config, *, progress_callback, stop_callback):
        return PipelineResult(
            run_id="run_guided_test",
            candidates=[],
            events=[],
            summary={
                "total_candidates": 3,
                "official_validation_attempted": 2,
                "official_validation_passed": 1,
                "officially_simulated": 1,
                "score_distribution": {"submit_candidate": 1},
                "gate_summary": {"BRAIN_HARD_GATES": {"pass": 1, "fail": 0}},
                "submission_ready": 1,
                "auto_submitted": 0,
            },
        )

    monkeypatch.setattr(guided_pipeline, "run_pipeline_from_config", fake_run_pipeline)

    result = pipeline._phase_core_pipeline(
        PipelineResult(run_id="run_guided_test", candidates=[], events=[], summary={})
    )
    pipeline._phase_finalize(result)

    assert pipeline.phases["validation"].status == "completed"
    assert pipeline.phases["gating"].status == "completed"
    history_path = tmp_path / "run_history" / "run_guided_test.json"
    assert history_path.is_file()
    history_payload = json.loads(history_path.read_text(encoding="utf-8"))
    assert history_payload["parameter_audit"]["schema_version"] == "parameter_audit_snapshot.v1"
    assert history_payload["parameter_audit"]["thresholds_zero_deviation"] is True
    assert pipeline.list_history()[0]["run_id"] == "run_guided_test"
    assert pipeline.list_history()[0]["parameter_audit"]["ok"] is True


def test_guided_pipeline_accepts_fixed_dataset_strategy(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    config.ops.settings.dataset = "pv1"
    config.ops.budget.dataset_strategy = "fixed"
    pipeline = GuidedPipeline(config)

    def fake_run_pipeline(run_config, *, progress_callback, stop_callback):
        return PipelineResult(run_id="run_guided_test", candidates=[], events=[], summary={})

    monkeypatch.setattr(guided_pipeline, "run_pipeline_from_config", fake_run_pipeline)

    result = pipeline._phase_core_pipeline(
        PipelineResult(run_id="run_guided_test", candidates=[], events=[], summary={})
    )

    assert result.run_id == "run_guided_test"


def test_guided_pipeline_forwards_core_progress_dicts_and_stop_callback(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    stop_requested = {"value": True}
    pipeline = GuidedPipeline(config, stop_callback=lambda: stop_requested["value"])
    progress_events = []
    pipeline.on_progress(lambda phase, status, data: progress_events.append((phase, status, data)))

    def fake_run_pipeline(run_config, *, progress_callback, stop_callback):
        assert stop_callback() is True
        progress_callback({
            "phase": "local_scoring",
            "percent": 40,
            "message": "scored one candidate",
            "alpha_id": "a1",
        })
        return PipelineResult(run_id="run_guided_test", candidates=[], events=[], summary={})

    monkeypatch.setattr(guided_pipeline, "run_pipeline_from_config", fake_run_pipeline)

    pipeline._phase_core_pipeline(PipelineResult(run_id="run_guided_test", candidates=[], events=[], summary={}))

    assert ("validation", "progress", {
        "phase": "local_scoring",
        "percent": 40,
        "message": "scored one candidate",
        "alpha_id": "a1",
    }) in progress_events
