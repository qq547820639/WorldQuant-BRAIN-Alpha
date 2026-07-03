"""Candidate generation payload builder."""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.config import RunConfig, resolve_default_dataset_id
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.errors import ValidationError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.alpha_quality import (
    build_alpha_output_config,
    diagnose_alpha_candidate,
    summarize_quality_diagnostics,
)
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
)
from brain_alpha_ops.research.field_quality import non_signal_generation_fields
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
    LocalBacktestEngine,
    PREFILTER_BACKTEST_DATES,
    PREFILTER_BACKTEST_SYMBOLS,
)
from brain_alpha_ops.research.local_backtest_gate import (
    apply_local_backtest_gate,
    blocked_local_gate,
)
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.scoring import build_scorecard
from brain_alpha_ops.web_candidates.audit import (
    attach_scientific_audit,
    scientific_audit_summary,
)
from brain_alpha_ops.web_candidates.decisions import annotate_candidate_decision
from brain_alpha_ops.web_config import (
    _MAX_CANDIDATES,
    _MAX_POOL_SIZE,
    bounded_query_float,
    bounded_query_int,
    payload_truthy,
)
from brain_alpha_ops.web_candidates.generation._generation_helpers import (
    RunConfigFromPayload,
    ToolboxFactory,
    RepositoryFactory,
    _REJECTED_CANDIDATE_PREVIEW_LIMIT,
    _candidate_pool_maintenance_requested,
    _candidate_rejected_by_local_gate,
    _candidate_rejection_reasons,
    _default_toolbox_factory,
    _rejected_reason_counts,
    _requested_generation_count,
    candidate_pool_automation_plan,
)

def generate_candidates_payload(
    payload: dict[str, Any],
    *,
    run_config_from_payload: RunConfigFromPayload,
    toolbox_factory: ToolboxFactory = _default_toolbox_factory,
    repository_factory: RepositoryFactory = ResearchRepository,
) -> dict[str, Any]:
    payload = dict(payload or {})
    run_config = run_config_from_payload(payload)
    dataset_id = str(payload.get("dataset_id") or run_config.ops.settings.dataset or "").strip()
    if not dataset_id:
        try:
            dataset_id = resolve_default_dataset_id(run_config.ops.storage_dir)
        except Exception as exc:
            return user_error_payload(
                exc,
                error_code="GENERATE_CANDIDATES_DATASET_ERROR",
                phase="web_generate_candidates",
            )
        run_config.ops.settings.dataset = dataset_id
    local_backtest_engine = LocalBacktestEngine(
        n_dates=PREFILTER_BACKTEST_DATES,
        n_symbols=PREFILTER_BACKTEST_SYMBOLS,
    )
    preferred_fields = [
        str(field).lower()
        for field in sorted(getattr(local_backtest_engine, "supported_fields", set()) or [])
        if str(field)
    ]
    preferred_operators = [
        str(operator).lower()
        for operator in sorted(getattr(local_backtest_engine, "supported_operators", set()) or [])
        if str(operator)
    ]
    target_pool_size = bounded_query_int(
        payload.get("target_pool_size", payload.get("targetPoolSize", run_config.ops.budget.retained_alpha_pool_size)),
        1,
        _MAX_POOL_SIZE,
    )
    existing_pool_size = bounded_query_int(
        payload.get("existing_pool_size", payload.get("existingPoolSize", 0)),
        0,
        _MAX_POOL_SIZE,
    )
    pool_deficit = max(0, target_pool_size - existing_pool_size)
    requested_count = _requested_generation_count(payload, pool_deficit=pool_deficit)
    args = {
        "count": requested_count,
        "dataset_id": dataset_id,
        "use_research_memory": payload_truthy(payload.get("use_research_memory", True)),
        "top_n": bounded_query_int(payload.get("top_n", 10), 1, 50),
        "min_success_rate": bounded_query_float(payload.get("min_success_rate", 0.0), 0.0, 1.0),
        "assistant_min_confidence": bounded_query_float(payload.get("assistant_min_confidence", 0.0), 0.0, 1.0),
    }
    if preferred_fields:
        args["preferred_fields"] = preferred_fields
        args["strict_preferred_fields"] = True
    if preferred_operators:
        args["preferred_operators"] = preferred_operators
        args["strict_preferred_operators"] = True
    for key in ("assistant_response", "assistant_raw_output", "assistant_guidance"):
        if key in payload:
            args[key] = payload[key]
    try:
        result = toolbox_factory(run_config).call("generate_candidates", args)
    except Exception as exc:
        return user_error_payload(
            exc,
            error_code="GENERATE_CANDIDATES_TOOLBOX_ERROR",
            phase="web_generate_candidates",
        )
    if not isinstance(result, dict):
        return user_error_payload(
            ValidationError("candidate generator returned a non-object response"),
            error_code="GENERATE_CANDIDATES_VALIDATION_ERROR",
            phase="web_generate_candidates",
        )
    if not result.get("ok"):
        return result

    alpha_output_config = build_alpha_output_config(
        run_config,
        dataset_id=dataset_id,
        generation_args=args,
    )
    candidates: list[dict[str, Any]] = []
    processed_candidates: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    raw_assistant_guidance = result.get("assistant_guidance")
    assistant_guidance = raw_assistant_guidance if isinstance(raw_assistant_guidance, dict) else {}
    assistant_guidance_applied = bool(assistant_guidance.get("applied"))
    assistant_guidance = ensure_assistant_guidance_digest(assistant_guidance) if assistant_guidance else {}
    for row in result.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        candidate = Candidate.from_dict(row)
        if not candidate.dataset_id:
            candidate.dataset_id = dataset_id
        candidate.local_quality = local_quality(candidate, run_config.ops.budget.min_local_quality_score)
        apply_local_backtest_gate(
            candidate,
            engine=local_backtest_engine,
            cache_key=candidate.dataset_id or run_config.ops.settings.dataset or "default",
            extract_fields=extract_fields,
            extract_operators=extract_operators,
            reject_unsupported=True,
            reject_failed_metrics=True,
        )
        non_signal_fields = non_signal_generation_fields(candidate)
        if non_signal_fields:
            local = dict(candidate.local_quality or {})
            reasons = list(local.get("reasons") or [])
            reason = "non_signal_generation_fields=" + ",".join(non_signal_fields[:8])
            if reason not in reasons:
                reasons.append(reason)
            local["passed"] = False
            local["reasons"] = reasons
            local["score"] = max(0.0, round(float(local.get("score", 0.0) or 0.0) - 8.0, 2))
            local["non_signal_generation_fields"] = non_signal_fields
            candidate.local_quality = local
        candidate.scorecard = build_scorecard(candidate, run_config.ops.thresholds, run_config.ops.scoring)
        candidate.alpha_output_config = alpha_output_config
        generation_risks = high_turnover_generation_risk_reasons(candidate.expression)
        if candidate.local_quality.get("passed") is False:
            candidate.lifecycle_status = "local_prefilter_rejected"
            candidate.gate = blocked_local_gate(list(candidate.local_quality.get("reasons") or []))
        else:
            candidate.lifecycle_status = "candidate_pool_retained"
        tags = list(candidate.source_tags or [])
        tag_values = ["local_only"]
        if assistant_guidance_applied:
            tag_values.extend(["assistant_guided", f"assistant_guidance_{assistant_guidance.get('guidance_digest', '')}"])
            submission = dict(candidate.submission or {})
            submission.update(assistant_guidance_candidate_metadata(assistant_guidance))
            candidate.submission = submission
        if generation_risks:
            tag_values.append("generation_risk_blocked")
        for tag in tag_values:
            if tag not in tags:
                tags.append(tag)
        candidate.source_tags = tags
        candidate.quality_diagnosis = diagnose_alpha_candidate(
            candidate,
            run_config=run_config,
            output_config=alpha_output_config,
        )
        candidate_payload = annotate_candidate_decision(
            candidate.to_dict(),
            min_official_score=run_config.ops.budget.min_prior_score_for_official_simulation,
            update_lifecycle=True,
        )
        feedback_sources = [
            "local_quality",
            "local_backtest_prefilter",
            "scorecard",
            "quality_gate",
        ]
        if assistant_guidance_applied:
            feedback_sources.append("assistant_guidance")
        candidate_payload = attach_scientific_audit(
            candidate_payload,
            operation="candidate_generation",
            source="local_candidate_generator",
            feedback_sources=feedback_sources,
            decision=candidate_payload.get("production_decision")
            if isinstance(candidate_payload.get("production_decision"), dict)
            else None,
        )
        candidate.lifecycle_status = candidate_payload.get("lifecycle_status", candidate.lifecycle_status)
        candidate.quality_diagnosis = candidate_payload.get("quality_diagnosis", candidate.quality_diagnosis)
        candidate.extra_fields = candidate_payload.get("extra_fields", candidate.extra_fields)
        processed_candidates.append(candidate_payload)
        if _candidate_rejected_by_local_gate(candidate_payload):
            rejected_candidates.append(candidate_payload)
        else:
            candidates.append(candidate_payload)

    quality_summary = summarize_quality_diagnostics(processed_candidates)
    rejected_reasons = _rejected_reason_counts(rejected_candidates)
    summary = {
        "generated_count": len(processed_candidates),
        "returned_count": len(candidates),
        "rejected_count": len(rejected_candidates),
        "rejected_reasons": rejected_reasons,
        "source": "local_candidate_generator",
        "assistant_guidance": assistant_guidance or result.get("assistant_guidance"),
        "local_only": True,
        "official_api_called": False,
        "alpha_output_config": alpha_output_config,
        "quality_summary": quality_summary,
        "qualified_count": quality_summary.get("qualified_count", 0),
        "invalid_count": quality_summary.get("invalid_count", 0),
        "local_valid_count": quality_summary.get("local_valid_count", 0),
        "generation_mode": "candidate_pool_refill",
        "target_pool_size": target_pool_size,
        "existing_pool_size": existing_pool_size,
        "pool_deficit": pool_deficit,
        "main_pool_count": min(target_pool_size, existing_pool_size + len(candidates)),
        "remaining_deficit": max(0, target_pool_size - existing_pool_size - len(candidates)),
        "requested_generation_count": requested_count,
        "automation": candidate_pool_automation_plan(
            payload,
            target_pool_size=target_pool_size,
            existing_pool_size=existing_pool_size,
            pool_deficit=pool_deficit,
            requested_count=requested_count,
        ),
        "scientific_audit": scientific_audit_summary(processed_candidates),
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
        "rejected_candidates_preview": rejected_candidates[:_REJECTED_CANDIDATE_PREVIEW_LIMIT],
        "summary": summary,
        "assistant_guidance": assistant_guidance or result.get("assistant_guidance"),
    }


