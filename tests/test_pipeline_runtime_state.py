from __future__ import annotations

from brain_alpha_ops.config import OpsConfig
from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
from brain_alpha_ops.research.pipeline_state import PipelineRuntimeState
from scripts.check_pipeline_runtime_state import check_pipeline_runtime_state


class _NoopAPI:
    pass


def test_pipeline_runtime_state_is_grouped_and_compatibly_bound(tmp_path):
    result = check_pipeline_runtime_state()

    assert result["ok"] is True
    assert result["schema_version"] == "pipeline_runtime_state_check.v1"
    assert result["init_self_assignment_count"] <= 5
    assert result["runtime_state_field_count"] >= 20
    assert result["bind_call_present"] is True
    assert result["findings"] == []


def test_alpha_research_pipeline_owns_runtime_state_container(tmp_path):
    config = OpsConfig(storage_dir=str(tmp_path))
    pipeline = AlphaResearchPipeline(config=config, api=_NoopAPI())

    assert isinstance(pipeline._runtime_state, PipelineRuntimeState)
    assert set(pipeline.__dict__) == {"_runtime_state", "_services_container"}
    assert pipeline.config is config
    assert pipeline.repository is not None
    assert pipeline.events == []
