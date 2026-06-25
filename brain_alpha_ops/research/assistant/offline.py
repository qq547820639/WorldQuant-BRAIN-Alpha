"""Deterministic offline assistant-style draft builder.

Contains ``build_offline_assistant_response`` — a deterministic local-only
draft that keeps the project useful when no external model client is
configured — plus its summary and confidence helpers.
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.research.robustness_context import (
    assistant_robustness_signals,
    robustness_evidence,
    robustness_gate_adjustment,
)

from ._constants import ASSISTANT_RESPONSE_SCHEMA_VERSION
from ._helpers import (
    _as_dict,
    _clamp,
    _duplicate_expressions,
    _float_value,
    _guidance_count,
    _guidance_digest,
    _guidance_outcomes,
    _guidance_success_rate,
    _number_items,
    _recent_backtest_records,
    _string_items,
    _strong_guidance_outcome,
    _unique_strings,
    _weak_guidance_outcome,
)


def build_offline_assistant_response(context_pack: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic assistant-style draft from local context only."""
    context = context_pack or {}
    latest = _as_dict(context.get("latest_result"))
    memory = _as_dict(context.get("research_memory"))
    expression_index = _as_dict(context.get("expression_index") or memory.get("expression_index"))
    focus = _as_dict(context.get("generation_focus"))
    cloud = _as_dict(context.get("cloud_alphas"))
    guardrails = _as_dict(context.get("risk_controls"))
    observability = _as_dict(context.get("observability"))
    robustness = _as_dict(context.get("robustness"))

    fields = _string_items(focus.get("fields"))[:5]
    operators = _string_items(focus.get("operators"))[:5]
    windows = _number_items(focus.get("windows"))[:5]
    guidance_outcomes = _guidance_outcomes(focus.get("guidance_outcomes") or memory.get("assistant_guidance_outcomes"))
    strong_guidance = _strong_guidance_outcome(guidance_outcomes)
    weak_guidance = _weak_guidance_outcome(guidance_outcomes)
    duplicate_expressions = _duplicate_expressions(expression_index.get("duplicates") or focus.get("duplicate_expressions"))
    backtest_records = _recent_backtest_records(latest.get("backtest_records") or context.get("backtest_records"))
    memory_samples = int(memory.get("total_candidates") or memory.get("guidance_sample_size") or 0)
    pending_backtests = int(latest.get("pending_backtest_count") or 0)
    cloud_stale = bool(cloud.get("is_stale") or guardrails.get("cloud_cache_stale"))
    observability_health_flags = _unique_strings(observability.get("health_flags") or [])
    observability_blocking_flags = _unique_strings(observability.get("blocking_flags") or [])
    observability_warning_flags = _unique_strings(observability.get("warning_flags") or [])
    observability_actions = _unique_strings(observability.get("recommended_actions") or observability.get("recommendations") or [])
    observability_risk_level = str(observability.get("risk_level") or "unknown")
    observability_backtest_failure_rate = _float_value(observability.get("backtest_failure_rate"))
    observability_retryable_errors = int(observability.get("retryable_error_count") or 0)
    observability_guard_blocked = int(observability.get("official_guard_blocked_count") or 0)
    observability_guard_validation_blocked = int(observability.get("official_guard_validation_blocked_count") or 0)
    observability_guard_simulation_blocked = int(observability.get("official_guard_simulation_blocked_count") or 0)
    robustness_signals = assistant_robustness_signals(robustness)
    robustness_flags = list(robustness_signals["flags"])

    actions = _unique_strings(context.get("recommended_next_actions") or [])
    actions.extend(observability_actions)
    actions.extend(robustness_signals["actions"])
    if fields or operators:
        actions.append("Bias the next candidate batch toward the strongest memory-supported fields/operators while reserving room for exploration.")
    if windows:
        actions.append("Start mutations with the preferred memory windows before trying wider lookback sweeps.")
    if strong_guidance:
        actions.append(
            f"Iterate on assistant guidance digest {strong_guidance.get('guidance_digest')}; "
            f"memory shows success_rate={strong_guidance.get('success_rate')} and avg_score={strong_guidance.get('avg_score')}."
        )
    if weak_guidance:
        actions.append(
            f"Reduce reliance on assistant guidance digest {weak_guidance.get('guidance_digest')} until it is revised or balanced with alternative hypotheses."
        )
    if cloud_stale and not any("cloud" in item.lower() for item in actions):
        actions.append("Refresh the cloud alpha cache before correlation-sensitive ranking or submission.")
    if pending_backtests and not any("pending" in item.lower() or "backtest" in item.lower() for item in actions):
        actions.append("Let pending backtests clear before producing near-duplicate variants.")
    if duplicate_expressions:
        actions.append("Use expression fingerprints to avoid repeating the most frequent canonical expressions already in local history.")
    if backtest_records:
        actions.append("Review the latest persisted backtest state records before changing simulation priority.")
    if "rate_limit_pressure" in observability_health_flags:
        actions.append("Pause or slow official/API calls until recent rate-limit pressure clears.")
    if "backtest_failure_rate_elevated" in observability_health_flags:
        actions.append("Fix the top persisted backtest failure modes before expanding official simulation volume.")
    if observability_blocking_flags:
        actions.append("Resolve blocking observability flags before submission-sensitive work.")
    if observability_guard_blocked:
        actions.append(
            "Review official-call guard history before more validation/simulation calls; "
            f"{observability_guard_blocked} recent duplicate-expression official calls were blocked."
        )
    if "anti_overfit_block" in robustness_flags:
        actions.append("Remove or materially revise anti-overfit blocked candidates before official simulation.")
    if "rolling_validation_weak" in robustness_flags:
        actions.append("Prioritize rolling-stable candidates before spending additional official backtest budget.")
    if not actions:
        actions.append("Run another local production cycle to collect enough evidence for model-guided recommendations.")
    actions = _unique_strings(actions)[:8]

    risk_flags = []
    if cloud_stale:
        risk_flags.append("cloud_cache_stale")
    if pending_backtests:
        risk_flags.append("pending_backtests")
    if guardrails.get("submit_requires_confirmation"):
        risk_flags.append("submit_requires_confirmation")
    if guardrails.get("cloud_sync_required"):
        risk_flags.append("cloud_sync_required")
    if guardrails.get("block_micro_variants"):
        risk_flags.append("micro_variant_block_enabled")
    if weak_guidance:
        risk_flags.append("weak_assistant_guidance_outcome")
    if duplicate_expressions:
        risk_flags.append("duplicate_expression_history")
    if backtest_records:
        risk_flags.append("persisted_backtest_state_available")
    if observability_guard_blocked:
        risk_flags.append("observability_official_call_guard_active")
    risk_flags.extend(robustness_flags)
    risk_flags.extend(observability_warning_flags)
    risk_flags.extend(observability_blocking_flags)
    risk_flags = _unique_strings(risk_flags)

    adjustments = []
    if fields:
        adjustments.append({
            "target": "fields",
            "value": fields[:3],
            "rationale": "Highest local research-memory support.",
        })
    if operators:
        adjustments.append({
            "target": "operators",
            "value": operators[:3],
            "rationale": "Most useful operators in the current memory guidance.",
        })
    if windows:
        adjustments.append({
            "target": "windows",
            "value": windows[:3],
            "rationale": "Preferred lookbacks observed in accepted or high-scoring local records.",
        })
    if strong_guidance:
        adjustments.append({
            "target": "assistant_guidance_digest",
            "value": strong_guidance.get("guidance_digest"),
            "rationale": "Best recorded assistant-guidance outcome in local research memory.",
        })
    if duplicate_expressions:
        adjustments.append({
            "target": "avoid_expression_fingerprints",
            "value": [row.get("expression_fingerprint", "") for row in duplicate_expressions[:3] if row.get("expression_fingerprint")],
            "rationale": "Canonical expression index shows repeated local/cloud/backtest history.",
        })
    if observability_health_flags:
        adjustments.append({
            "target": "observability_health_flags",
            "value": observability_health_flags[:5],
            "rationale": "Research observability diagnostics should shape generation and official-call pacing.",
        })
    if observability_guard_blocked:
        adjustments.append({
            "target": "official_call_guard",
            "value": {
                "blocked_count": observability_guard_blocked,
                "validation_blocked_count": observability_guard_validation_blocked,
                "simulation_blocked_count": observability_guard_simulation_blocked,
            },
            "rationale": "Duplicate-expression official-call guard history should slow or diversify official validation/simulation targets.",
        })
    robustness_adjustment = robustness_gate_adjustment(robustness_signals)
    if robustness_adjustment:
        adjustments.append(robustness_adjustment)
    failures = focus.get("failure_patterns") if isinstance(focus.get("failure_patterns"), list) else []
    if failures:
        first = _as_dict(failures[0])
        adjustments.append({
            "target": "failure_mode",
            "value": first.get("reason") or "unknown",
            "rationale": "Most frequent recorded failure pattern should be handled before broad exploration.",
        })

    questions = []
    if not fields:
        questions.append("Which field family should be explored first to seed research memory?")
    if cloud_stale:
        questions.append("Should the cloud cache be refreshed before the next submission-sensitive step?")
    if pending_backtests:
        questions.append("Should generation slow down until pending backtests clear?")
    if observability_blocking_flags:
        questions.append("Should blocking observability flags be resolved before any submission-sensitive step?")
    if observability_guard_blocked:
        questions.append("Should the next official-call batch exclude all recent guard-blocked expression fingerprints?")
    if robustness_flags:
        questions.append("Should robustness-flagged candidates be revised before the next official simulation batch?")

    summary = _offline_summary(
        fields,
        operators,
        windows,
        cloud_stale,
        pending_backtests,
        memory_samples,
        strong_guidance,
        weak_guidance,
    )
    if observability_risk_level in {"medium", "high", "blocked"}:
        summary += f" Observability risk is {observability_risk_level}; review {', '.join(observability_warning_flags[:3] or observability_health_flags[:3])}."
    if observability_guard_blocked:
        summary += f" Official-call guard blocked {observability_guard_blocked} recent duplicate-expression attempts."
    if robustness_flags:
        summary += " Robustness flags active: " + ", ".join(robustness_flags[:3]) + "."
    confidence = _offline_confidence(
        memory_samples,
        fields,
        operators,
        windows,
        cloud_stale,
        pending_backtests,
        strong_guidance,
        weak_guidance,
    )
    return {
        "ok": True,
        "schema_version": ASSISTANT_RESPONSE_SCHEMA_VERSION,
        "source": "offline_context_heuristic",
        "generated_at": utc_now(),
        "summary": summary,
        "recommended_next_actions": actions,
        "risk_flags": risk_flags,
        "candidate_adjustments": adjustments,
        "follow_up_questions": questions,
        "confidence": confidence,
        "evidence": {
            "memory_sample_size": memory_samples,
            "latest_candidate_count": int(latest.get("candidate_count") or 0),
            "pending_backtest_count": pending_backtests,
            "cloud_count": int(cloud.get("count") or 0),
            "cloud_stale": cloud_stale,
            "assistant_guidance_outcome_count": len(guidance_outcomes),
            "top_guidance_digest": _guidance_digest(strong_guidance) or _guidance_digest(guidance_outcomes[0] if guidance_outcomes else {}),
            "top_guidance_success_rate": _guidance_success_rate(strong_guidance or (guidance_outcomes[0] if guidance_outcomes else {})),
            "weak_guidance_digest": _guidance_digest(weak_guidance),
            "duplicate_expression_count": int(expression_index.get("duplicate_expression_count") or 0),
            "recent_backtest_record_count": len(backtest_records),
            "observability_risk_level": observability_risk_level,
            "observability_health_flags": observability_health_flags,
            "observability_blocking_flags": observability_blocking_flags,
            "observability_backtest_failure_rate": observability_backtest_failure_rate,
            "observability_retryable_error_count": observability_retryable_errors,
            "observability_official_guard_blocked_count": observability_guard_blocked,
            "observability_official_guard_validation_blocked_count": observability_guard_validation_blocked,
            "observability_official_guard_simulation_blocked_count": observability_guard_simulation_blocked,
            **robustness_evidence(robustness_signals),
        },
    }


def _offline_summary(
    fields: list[str],
    operators: list[str],
    windows: list[int | float],
    cloud_stale: bool,
    pending_backtests: int,
    memory_samples: int,
    strong_guidance: dict[str, Any] | None = None,
    weak_guidance: dict[str, Any] | None = None,
) -> str:
    parts = []
    if fields or operators:
        focus_bits = []
        if fields:
            focus_bits.append(f"fields {', '.join(fields[:3])}")
        if operators:
            focus_bits.append(f"operators {', '.join(operators[:3])}")
        parts.append("Local memory favors " + " and ".join(focus_bits) + ".")
    elif memory_samples:
        parts.append("Local memory exists but has no strong field/operator focus yet.")
    else:
        parts.append("Research memory is sparse; collect more local evidence before high-conviction recommendations.")
    if windows:
        parts.append(f"Preferred windows include {', '.join(str(item) for item in windows[:3])}.")
    if strong_guidance:
        parts.append(
            f"Assistant guidance digest {_guidance_digest(strong_guidance)} has success_rate "
            f"{_guidance_success_rate(strong_guidance)} over {_guidance_count(strong_guidance)} candidates."
        )
    if weak_guidance:
        parts.append(
            f"Guidance digest {_guidance_digest(weak_guidance)} has weak recorded outcomes and should be revised before heavy reuse."
        )
    if cloud_stale:
        parts.append("Cloud cache is stale and should be refreshed before submission-sensitive work.")
    if pending_backtests:
        parts.append(f"{pending_backtests} candidates are waiting for backtest results.")
    return " ".join(parts)


def _offline_confidence(
    memory_samples: int,
    fields: list[str],
    operators: list[str],
    windows: list[int | float],
    cloud_stale: bool,
    pending_backtests: int,
    strong_guidance: dict[str, Any] | None = None,
    weak_guidance: dict[str, Any] | None = None,
) -> float:
    score = 0.35
    score += min(memory_samples, 100) / 100 * 0.20
    if fields:
        score += 0.12
    if operators:
        score += 0.12
    if windows:
        score += 0.08
    if strong_guidance:
        score += 0.05
    if weak_guidance:
        score -= 0.06
    if cloud_stale:
        score -= 0.08
    if pending_backtests:
        score -= 0.05
    return round(_clamp(score, 0.05, 0.95), 2)
