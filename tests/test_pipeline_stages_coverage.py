from __future__ import annotations

from types import SimpleNamespace

import pytest

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research import pipeline_stages
from brain_alpha_ops.research.pipeline_stages import (
    GenerationStage,
    LocalScoringStage,
    OfficialValidationStage,
    PipelineStage,
    PipelineStagesOrchestrator,
    QualityGateStage,
    SimulationStage,
    StageStatus,
    SubmissionStage,
    _merge_context,
    build_full_pipeline,
    build_local_only_pipeline,
)


class _Generator:
    def __init__(self):
        self.experience = None
        self.observability = None

    def set_experience_guidance(self, guidance):
        self.experience = guidance

    def set_observability_guidance(self, guidance):
        self.observability = guidance

    def generate(self, count):
        return [
            Candidate("a1", "rank(close)", "Momentum", "test", data_fields=["close"], operators=["rank"]),
            Candidate("a2", "rank(open)", "Value", "test", data_fields=["open"], operators=["rank"]),
        ][:count]


class _API:
    def __init__(self, *, fail_validation=False, simulation_status="COMPLETED", submit_check="PASS"):
        self.fail_validation = fail_validation
        self.simulation_status = simulation_status
        self.submit_check = submit_check
        self.submissions = []

    def authenticate(self):
        return True

    def validate_expression(self, expression, settings):
        if self.fail_validation:
            raise RuntimeError("validation down")
        return {"status": "PASS" if "rank" in expression else "FAIL", "alpha_id": f"official_{len(expression)}"}

    def submit_simulation(self, expression, settings):
        return f"sim_{len(expression)}"

    def poll_simulation(self, sim_id):
        return self.simulation_status

    def fetch_result(self, sim_id):
        return {"sharpe": 1.8, "fitness": 1.4, "turnover": 0.2, "self_correlation": 0.2}

    def check_alpha(self, official_alpha_id):
        return {"status": self.submit_check}

    def submit_alpha(self, official_alpha_id, expression, settings):
        self.submissions.append((official_alpha_id, expression, settings))
        return {"ok": True, "alpha_id": official_alpha_id}


class _FakeLedger:
    records = []
    allowed = True

    def __init__(self, storage_dir):
        self.storage_dir = storage_dir

    def assess(self, candidate, policy, mode):
        return {"allowed": self.allowed, "failed_reasons": [] if self.allowed else ["blocked"]}

    def record(self, candidate, result, mode):
        self.records.append((candidate.alpha_id, result, mode))


class _BrokenStage(PipelineStage):
    stage_name = "broken"

    def execute(self, ctx):
        raise RuntimeError("boom")


class _OkStage(PipelineStage):
    stage_name = "ok"

    def execute(self, ctx):
        ctx.ok_ran = True
        return ctx


def _pipeline(tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    config.ops.budget.max_candidates_per_cycle = 2
    config.ops.budget.min_local_quality_score = 0
    config.ops.budget.max_official_validations_per_cycle = 2
    config.ops.budget.max_official_simulations_per_cycle = 2
    config.ops.official_api.poll_attempts = 1
    config.ops.official_api.poll_interval_seconds = 0
    config.ops.submission_policy.max_auto_submissions_per_run = 2
    pipeline = SimpleNamespace(
        ops=config.ops,
        auto_submit=True,
        _generator=_Generator(),
        _candidate_pool=[],
        _current_memory_guidance={"digest": "memory"},
        _current_observability_guidance={"risk": "low"},
    )
    return pipeline


def test_generation_stage_applies_guidance_and_merges_returned_context(tmp_path):
    pipeline = _pipeline(tmp_path)

    result = GenerationStage().run(pipeline)

    assert result.status == StageStatus.COMPLETED
    assert [candidate.alpha_id for candidate in pipeline._candidate_pool] == ["a1", "a2"]
    assert pipeline._generator.experience == {"digest": "memory"}
    assert pipeline._generator.observability == {"risk": "low"}
    assert result.to_dict()["status"] == "COMPLETED"

    target = SimpleNamespace(a=1)
    source = SimpleNamespace(a=2, _private=3)
    source.method = lambda: None
    _merge_context(target, source)
    assert target.a == 2
    assert not hasattr(target, "_private")


def test_local_validation_simulation_and_quality_gate_stages(tmp_path):
    pipeline = _pipeline(tmp_path)
    GenerationStage().execute(pipeline)

    LocalScoringStage().execute(pipeline)
    assert all(candidate.lifecycle_status == "scored" for candidate in pipeline._candidate_pool)

    pipeline._api = _API()
    OfficialValidationStage().execute(pipeline)
    assert all(candidate.lifecycle_status == "validated" for candidate in pipeline._candidate_pool)
    assert all(candidate.official_alpha_id for candidate in pipeline._candidate_pool)

    SimulationStage().execute(pipeline)
    assert all(candidate.lifecycle_status == "simulation_completed" for candidate in pipeline._candidate_pool)
    assert all(candidate.official_metrics for candidate in pipeline._candidate_pool)

    QualityGateStage().execute(pipeline)
    assert all(candidate.lifecycle_status.startswith("gated") for candidate in pipeline._candidate_pool)
    scores = [candidate.scorecard["total_score"] for candidate in pipeline._candidate_pool]
    assert scores == sorted(scores, reverse=True)


def test_official_and_simulation_stages_handle_missing_api_and_errors(tmp_path):
    pipeline = _pipeline(tmp_path)
    pipeline._candidate_pool = [Candidate("a1", "rank(close)", "Momentum", "test")]

    assert OfficialValidationStage().execute(pipeline) is pipeline
    assert SimulationStage().execute(pipeline) is pipeline

    pipeline._api = _API(fail_validation=True)
    OfficialValidationStage().execute(pipeline)
    assert pipeline._candidate_pool[0].lifecycle_status == "validation_error"

    pipeline._candidate_pool[0].lifecycle_status = "validated"
    pipeline._api = _API(simulation_status="FAILED")
    SimulationStage().execute(pipeline)
    assert pipeline._candidate_pool[0].lifecycle_status == "simulation_failed"


def test_submission_stage_honors_auto_submit_safety_and_precheck(monkeypatch, tmp_path):
    pipeline = _pipeline(tmp_path)
    candidate = Candidate("a1", "rank(close)", "Momentum", "test")
    candidate.lifecycle_status = "gated:submit_candidate"
    candidate.decision_band = "submit_candidate"
    candidate.official_alpha_id = "official_a1"
    pipeline._candidate_pool = [candidate]
    pipeline._api = _API()
    _FakeLedger.records = []
    _FakeLedger.allowed = True
    monkeypatch.setattr("brain_alpha_ops.research.safety.SubmissionLedger", _FakeLedger)

    SubmissionStage().execute(pipeline)
    assert candidate.lifecycle_status == "submitted"
    assert _FakeLedger.records == [("a1", {"ok": True, "alpha_id": "official_a1"}, "auto")]

    candidate.lifecycle_status = "gated:submit_candidate"
    _FakeLedger.records = []
    _FakeLedger.allowed = False
    SubmissionStage().execute(pipeline)
    assert _FakeLedger.records == []

    pipeline._api = _API(submit_check="FAIL")
    _FakeLedger.allowed = True
    SubmissionStage().execute(pipeline)
    assert _FakeLedger.records == []

    pipeline.auto_submit = False
    assert SubmissionStage().execute(pipeline) is pipeline
    pipeline._api = None
    pipeline.auto_submit = True
    assert SubmissionStage().execute(pipeline) is pipeline


def test_orchestrator_summaries_and_prebuilt_pipelines(tmp_path):
    pipeline = _pipeline(tmp_path)
    orchestrator = PipelineStagesOrchestrator().add_stage(_OkStage()).add_stage(_BrokenStage()).add_stage(_OkStage())

    results = orchestrator.run(pipeline)
    summary = orchestrator.summary(results)

    assert [result.status for result in results] == [StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.SKIPPED]
    assert summary["schema_version"] == pipeline_stages.STAGE_SCHEMA_VERSION
    assert summary["overall"] == "FAIL"
    assert summary["completed"] == 1
    assert len(build_full_pipeline().stages) == 6
    assert [stage.stage_name for stage in build_local_only_pipeline().stages] == ["generation", "local_scoring", "quality_gate"]


def test_pipeline_stage_base_requires_execute():
    with pytest.raises(TypeError):
        PipelineStage()
