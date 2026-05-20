"""Candidate generation payload service for the local web console."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from brain_alpha_ops.agent_tools import BrainAlphaToolbox
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.generator import local_quality
from brain_alpha_ops.research.guidance import (
    assistant_guidance_candidate_metadata,
    ensure_assistant_guidance_digest,
)
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.scoring import build_scorecard
from brain_alpha_ops.web_config import (
    _MAX_CANDIDATES,
    bounded_query_float,
    bounded_query_int,
    payload_truthy,
)


class ToolboxLike(Protocol):
    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ToolboxFactory = Callable[[RunConfig], ToolboxLike]
RepositoryFactory = Callable[[str], ResearchRepository]


def _default_toolbox_factory(run_config: RunConfig) -> ToolboxLike:
    return BrainAlphaToolbox(run_config=run_config, allow_live_api=False, allow_submit=False)


def generate_candidates_payload(
    payload: dict[str, Any],
    *,
    run_config_from_payload: RunConfigFromPayload,
    toolbox_factory: ToolboxFactory = _default_toolbox_factory,
    repository_factory: RepositoryFactory = ResearchRepository,
) -> dict[str, Any]:
    payload = dict(payload or {})
    run_config = run_config_from_payload(payload)
    args = {
        "count": bounded_query_int(payload.get("count", payload.get("candidates", 10)), 1, _MAX_CANDIDATES),
        "dataset_id": str(payload.get("dataset_id") or run_config.ops.settings.dataset or ""),
        "use_research_memory": payload_truthy(payload.get("use_research_memory", True)),
        "top_n": bounded_query_int(payload.get("top_n", 10), 1, 50),
        "min_success_rate": bounded_query_float(payload.get("min_success_rate", 0.0), 0.0, 1.0),
        "assistant_min_confidence": bounded_query_float(payload.get("assistant_min_confidence", 0.0), 0.0, 1.0),
    }
    for key in ("assistant_response", "assistant_raw_output", "assistant_guidance"):
        if key in payload:
            args[key] = payload[key]
    result = toolbox_factory(run_config).call("generate_candidates", args)
    if not result.get("ok"):
        return result

    candidates: list[dict[str, Any]] = []
    assistant_guidance = result.get("assistant_guidance") if isinstance(result.get("assistant_guidance"), dict) else {}
    assistant_guidance_applied = bool(assistant_guidance.get("applied"))
    assistant_guidance = ensure_assistant_guidance_digest(assistant_guidance) if assistant_guidance else {}
    for row in result.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        candidate = Candidate.from_dict(row)
        candidate.local_quality = local_quality(candidate, run_config.ops.budget.min_local_quality_score)
        build_scorecard(candidate, run_config.ops.thresholds, run_config.ops.scoring)
        candidate.lifecycle_status = "assistant_generated" if assistant_guidance_applied else "generated"
        tags = list(candidate.source_tags or [])
        tag_values = ["local_only"]
        if assistant_guidance_applied:
            tag_values.extend(["assistant_guided", f"assistant_guidance_{assistant_guidance.get('guidance_digest', '')}"])
            submission = dict(candidate.submission or {})
            submission.update(assistant_guidance_candidate_metadata(assistant_guidance))
            candidate.submission = submission
        for tag in tag_values:
            if tag not in tags:
                tags.append(tag)
        candidate.source_tags = tags
        candidates.append(candidate.to_dict())

    summary = {
        "generated_count": len(candidates),
        "source": "local_candidate_generator",
        "assistant_guidance": assistant_guidance or result.get("assistant_guidance"),
        "local_only": True,
        "official_api_called": False,
    }
    if assistant_guidance_applied and assistant_guidance:
        repository_factory(run_config.ops.storage_dir).save_assistant_guidance(
            assistant_guidance,
            source="web_generate_candidates",
        )
    return {
        "ok": True,
        "count": len(candidates),
        "candidates": candidates,
        "summary": summary,
        "assistant_guidance": assistant_guidance or result.get("assistant_guidance"),
    }
