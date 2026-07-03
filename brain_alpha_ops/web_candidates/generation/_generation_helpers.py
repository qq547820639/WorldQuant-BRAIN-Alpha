"""Helper functions and types for candidate generation."""
from __future__ import annotations

from typing import Any, Callable, Protocol

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.alpha_quality import (
    build_alpha_output_config,
    diagnose_alpha_candidate,
    summarize_quality_diagnostics,
)
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
)
from brain_alpha_ops.research.generator import (
    extract_fields,
    extract_operators,
    local_quality,
)
from brain_alpha_ops.research.guidance import (
    assistant_guidance_candidate_metadata,
    ensure_assistant_guidance_digest,
)
from brain_alpha_ops.research.local_backtest_engine import (
    PREFILTER_BACKTEST_DATES,
    PREFILTER_BACKTEST_SYMBOLS,
)
from brain_alpha_ops.research.local_backtest_gate import (
    apply_local_backtest_gate,
    blocked_local_gate,
)
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.web_candidates.audit import (
    attach_scientific_audit,
    scientific_audit_summary,
)
from brain_alpha_ops.web_config import (
    _MAX_CANDIDATES,
    _MAX_POOL_SIZE,
    bounded_query_float,
    bounded_query_int,
    payload_truthy,
)
from brain_alpha_ops.web_payload_validation import MAX_GENERATE_CANDIDATES

_REJECTED_CANDIDATE_PREVIEW_LIMIT = 20


class ToolboxLike(Protocol):
    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ToolboxFactory = Callable[[RunConfig], ToolboxLike]
RepositoryFactory = Callable[[str], ResearchRepository]


def _default_toolbox_factory(run_config: RunConfig) -> ToolboxLike:
    from brain_alpha_ops.agent_tools import BrainAlphaToolbox
    return BrainAlphaToolbox(run_config=run_config, allow_live_api=False, allow_submit=False)


def candidate_pool_automation_plan(
    payload: dict[str, Any],
    *,
    target_pool_size: int,
    existing_pool_size: int,
    pool_deficit: int,
    requested_count: int,
) -> dict[str, Any]:
    mode = str(payload.get("automation_mode") or payload.get("automationMode") or "").strip()
    maintain_pool = mode == "maintain_candidate_pool"
    auto_simulate = False
    auto_check = False
    return {
        "mode": mode or "generate_candidates",
        "maintain_candidate_pool": maintain_pool,
        "auto_simulate_after_generation": auto_simulate,
        "auto_check_after_simulation": auto_check,
        "target_pool_size": target_pool_size,
        "existing_pool_size": existing_pool_size,
        "pool_deficit": pool_deficit,
        "requested_generation_count": requested_count,
        "next_steps": [],
        "producer_can_continue_while_validator_runs": True,
        "submit_allowed": False,
    }


def _candidate_pool_maintenance_requested(payload: dict[str, Any]) -> bool:
    mode = str(payload.get("automation_mode") or payload.get("automationMode") or "").strip()
    return mode == "maintain_candidate_pool"


def _requested_generation_count(payload: dict[str, Any], *, pool_deficit: int) -> int:
    count_source = payload.get("count", payload.get("candidates"))
    if count_source is not None:
        return bounded_query_int(count_source, 1, _MAX_CANDIDATES)
    if _candidate_pool_maintenance_requested(payload):
        return bounded_query_int(max(1, pool_deficit), 1, MAX_GENERATE_CANDIDATES)
    return 10




def _candidate_rejected_by_local_gate(candidate: dict[str, Any]) -> bool:
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    if diagnosis.get("local_candidate_valid") is False:
        return True
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        return True
    support = local_quality.get("local_backtest_support") if isinstance(local_quality.get("local_backtest_support"), dict) else {}
    if support.get("supported") is False:
        return True
    local_backtest = local_quality.get("local_backtest") if isinstance(local_quality.get("local_backtest"), dict) else {}
    if local_backtest.get("pass_local") is False:
        return True
    return False


def _rejected_reason_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        for reason in _candidate_rejection_reasons(candidate):
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _candidate_rejection_reasons(candidate: dict[str, Any]) -> list[str]:
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    reasons = [
        str(reason or "").strip()
        for reason in diagnosis.get("blocking_reasons") or []
        if str(reason or "").strip()
    ]
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    for reason in local_quality.get("reasons") or []:
        text = str(reason or "").strip()
        if text:
            reasons.append(text.split(":", 1)[0])
    local_backtest = local_quality.get("local_backtest") if isinstance(local_quality.get("local_backtest"), dict) else {}
    if local_backtest.get("pass_local") is False:
        reasons.append("local_backtest_failed")
    return sorted(set(reasons)) or ["local_candidate_invalid"]
