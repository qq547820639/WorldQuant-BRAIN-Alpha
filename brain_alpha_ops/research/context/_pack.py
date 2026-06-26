"""LLM-ready context packs — top-level pack builder.

``build_assistant_context_pack`` combines run configuration, latest local
results, cloud alpha cache summaries, and research memory guidance into a
payload that an assistant can consume before proposing or generating alphas.
"""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.observability import (
    build_research_observability_snapshot,
)
from brain_alpha_ops.research.robustness_context import (
    build_robustness_context,
    latest_candidate_rows,
)
from brain_alpha_ops.research.context._compliance import _compliance_context
from brain_alpha_ops.research.context._helpers import _cloud_snapshot_from_storage, _latest_result_from_storage
from brain_alpha_ops.research.context._sections import (
    _cloud_context,
    _expression_index_context,
    _generation_focus,
    _latest_result_context,
    _memory_context,
    _next_actions,
    _prompt_diagnostics,
    _risk_controls,
    _run_config_context,
    observability_context,
    render_context_prompt,
)

ASSISTANT_CONTEXT_SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "cache_dir",
    "cookie",
    "credential",
    "password",
    "path",
    "secret",
    "storage_dir",
    "token",
)

def build_assistant_context_pack(
    run_config: RunConfig | None = None,
    *,
    latest_result_snapshot: dict[str, Any] | None = None,
    cloud_alpha_snapshot: dict[str, Any] | None = None,
    memory_summary: dict[str, Any] | None = None,
    memory_guidance: dict[str, Any] | None = None,
    observability_snapshot: dict[str, Any] | None = None,
    limit: int = 5000,
    top_n: int = 10,
    include_prompt: bool = True,
    include_sensitive: bool = False,
) -> dict[str, Any]:
    """Build a prompt-ready context pack for an alpha research assistant."""
    config = run_config or load_run_config()
    storage_dir = str(config.ops.storage_dir)
    memory = ResearchMemory(storage_dir)

    summary = memory_summary if memory_summary is not None else memory.summary(limit=limit, top_n=top_n)
    guidance = memory_guidance if memory_guidance is not None else memory.generation_guidance(limit=limit, top_n=top_n, summary=summary)
    latest = latest_result_snapshot if latest_result_snapshot is not None else _latest_result_from_storage(storage_dir)
    cloud = cloud_alpha_snapshot if cloud_alpha_snapshot is not None else _cloud_snapshot_from_storage(storage_dir, top_n=top_n)
    observability = observability_snapshot if observability_snapshot is not None else build_research_observability_snapshot(storage_dir, limit=limit, top_n=top_n)
    latest_context = _latest_result_context(latest)
    robustness = build_robustness_context(latest_candidate_rows(latest), top_n=top_n)

    pack = {
        "ok": True,
        "schema_version": "assistant_context_pack.v1",
        "source": "local_config_run_history_cloud_memory",
        "generated_at": utc_now(),
        "storage_dir": storage_dir,
        "mission": {
            "role": "quant_investment_ai_assistant",
            "objective": "Generate, critique, and prioritize WorldQuant BRAIN FASTEXPR alpha ideas using local evidence before live API calls.",
            "operating_mode": "local_first_memory_guided_research",
        },
        "run_config": _run_config_context(config),
        "latest_result": latest_context,
        "cloud_alphas": _cloud_context(cloud, top_n=top_n),
        "research_memory": _memory_context(summary, guidance, top_n=top_n),
        "expression_index": _expression_index_context(
            summary.get("expression_index") if isinstance(summary, dict) else {},
            top_n=top_n,
        ),
        "observability": observability_context(observability, top_n=top_n),
        "robustness": robustness,
        "generation_focus": _generation_focus(guidance, summary, top_n=top_n),
        "risk_controls": _risk_controls(config, cloud),
        "recommended_next_actions": _next_actions(summary, guidance, latest, cloud, robustness=robustness),
        "compliance": _compliance_context(config),
    }
    pack["prompt_diagnostics"] = _prompt_diagnostics(pack, top_n=top_n)
    if not include_sensitive:
        pack = _redact_assistant_context_pack(pack)
    if include_prompt:
        pack["prompt"] = render_context_prompt(pack)
    return pack

def _redact_assistant_context_pack(pack: dict[str, Any]) -> dict[str, Any]:
    redacted_keys: set[str] = set()
    redacted = redact_data(
        pack,
        key_fragments=ASSISTANT_CONTEXT_SENSITIVE_KEY_FRAGMENTS,
        redacted_keys=redacted_keys,
    )
    if not isinstance(redacted, dict):
        return {}
    redacted.pop("storage_dir", None)
    redacted_keys.add("storage_dir")
    redacted["sensitive_fields_redacted"] = sorted(redacted_keys)
    return redacted
