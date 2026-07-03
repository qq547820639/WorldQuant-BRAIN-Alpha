"""Assistant, snapshot facade, and runtime snapshots.

Consolidated from the former ``web_assistant_snapshots/`` subpackage. Re-exports
shared logger/type aliases, research snapshots, run-history replay audit, and
user-profile snapshot helpers from ``web_assistant_snapshots_run_history`` and
defines the assistant guidance/payload snapshot builders directly.
"""
from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    build_assistant_request_pack,
    parse_assistant_response,
)
from brain_alpha_ops.research.context import build_assistant_context_pack
from brain_alpha_ops.research.guidance import (
    assistant_guidance_outcome_status,
    assistant_guidance_scoring_eligibility,
    assistant_guidance_scoring_policy,
    ensure_assistant_guidance_digest,
)
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.repository import ResearchRepository

from brain_alpha_ops.web.misc.web_assistant_snapshots_run_history import (
    BoundedFloat,
    LoadConfig,
    PayloadTruthy,
    ReadStorageJsonl,
    RunConfigFromPayload,
    SafeErrorMessage,
    Snapshot,
    StoragePath,
    WebError,
    _bounded_float,
    _default_web_error,
    _payload_truthy,
    _prompt_run_public_row,
    _run_history_candidate_keys,
    _run_history_candidate_payload_rows,
    _run_history_candidate_rows,
    _run_history_candidate_total,
    _run_history_decision_action_counts,
    _run_history_expression_digest,
    _run_history_expression_key,
    _run_history_lifecycle_rows,
    _run_history_matching_lifecycle_count,
    _run_history_reason_counts,
    _run_history_replay_audit,
    _run_history_result_payload,
    _run_history_workflow_queue_counts,
    durable_job_rows,
    latest_result_snapshot,
    latest_run_history_path,
    logger,
    prompt_run_ledger_snapshot,
    research_knowledge_snapshot,
    research_memory_snapshot,
    research_observability_snapshot,
    user_profile_snapshot,
)


def assistant_guidance_snapshot(
    *,
    limit: int = 100,
    min_confidence: float | None = None,
    load_config: LoadConfig = load_run_config,
    bounded_query_float: BoundedFloat = _bounded_float,
    payload_truthy: PayloadTruthy = _payload_truthy,
    read_storage_jsonl: ReadStorageJsonl | None = None,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        budget = config.ops.budget
        configured_min_confidence = bounded_query_float(
            getattr(budget, "assistant_guidance_min_confidence", 0.6),
            0.0,
            1.0,
        )
        threshold = configured_min_confidence if min_confidence is None else bounded_query_float(min_confidence, 0.0, 1.0)
        scoring_policy = assistant_guidance_scoring_policy(config.ops.scoring)
        memory = ResearchMemory(config.ops.storage_dir)
        guidance = memory.latest_assistant_guidance(
            limit=limit,
            min_confidence=threshold,
        )
        memory_summary = memory.summary(limit=5000, top_n=10)
        history = read_storage_jsonl("assistant_guidance.jsonl", limit=limit) if read_storage_jsonl else []
        outcomes_by_guidance = {
            str(row.get("guidance_digest") or ""): row
            for row in memory_summary.get("assistant_guidance_outcomes", [])
            if row.get("guidance_digest")
        }
        history_items = assistant_guidance_history(
            history,
            min_confidence=threshold,
            scoring_policy=scoring_policy,
            outcomes_by_guidance=outcomes_by_guidance,
            bounded_query_float=bounded_query_float,
            payload_truthy=payload_truthy,
        )
        return {
            "ok": True,
            "schema_version": "assistant_guidance_snapshot.v1",
            "enabled": bool(getattr(budget, "use_assistant_guidance", True)),
            "configured_min_confidence": configured_min_confidence,
            "min_confidence": threshold,
            "history_count": len(history),
            "history_limit": limit,
            "scoring_policy": scoring_policy,
            "score_adjustment_eligibility": assistant_guidance_scoring_eligibility(
                guidance,
                guidance.get("historical_outcome") if isinstance(guidance, dict) else {},
                scoring_policy,
            ),
            "guidance": guidance,
            "history": history_items,
            "outcomes": memory_summary.get("assistant_guided", {}),
            "outcomes_by_guidance": memory_summary.get("assistant_guidance_outcomes", []),
        }
    except Exception as exc:
        return web_error(exc, "ASSISTANT_GUIDANCE_ERROR")


def assistant_guidance_history(
    rows: list[dict[str, Any]],
    *,
    min_confidence: float,
    scoring_policy: dict[str, Any] | None = None,
    outcomes_by_guidance: dict[str, dict[str, Any]] | None = None,
    bounded_query_float: BoundedFloat = _bounded_float,
    payload_truthy: PayloadTruthy = _payload_truthy,
) -> list[dict[str, Any]]:
    threshold = bounded_query_float(min_confidence, 0.0, 1.0)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        guidance = row.get("guidance") if isinstance(row.get("guidance"), dict) else row
        if not isinstance(guidance, dict):
            continue
        guidance = ensure_assistant_guidance_digest(guidance)
        digest = row.get("guidance_digest") or guidance.get("guidance_digest")
        confidence = bounded_query_float(guidance.get("confidence", 1.0), 0.0, 1.0)
        usable = guidance.get("ok") is not False and payload_truthy(guidance.get("usable", True))
        has_bias = bool(
            guidance.get("top_fields")
            or guidance.get("top_operators")
            or guidance.get("preferred_windows")
            or guidance.get("field_combinations")
        )
        outcomes = (outcomes_by_guidance or {}).get(str(digest), {})
        outcome_status = assistant_guidance_outcome_status(outcomes)
        scoring_eligibility = assistant_guidance_scoring_eligibility(guidance, outcomes, scoring_policy or {})
        items.append(
            {
                "history_index": index,
                "timestamp": row.get("timestamp") or row.get("persisted_at") or "",
                "source": row.get("source") or guidance.get("persistence_source") or guidance.get("source") or "assistant_guidance_jsonl",
                "guidance_digest": digest,
                "usable": usable,
                "meets_min_confidence": confidence >= threshold,
                "has_generator_bias": has_bias,
                "has_healthy_outcome": outcome_status != "weak",
                "score_adjustment_eligible": scoring_eligibility.get("eligible", False),
                "score_adjustment_reason": scoring_eligibility.get("reason", ""),
                "historical_outcome_status": outcome_status,
                "confidence": confidence,
                "sample_size": guidance.get("sample_size") or 0,
                "summary": guidance.get("summary") or "",
                "reason": guidance.get("reason") or "",
                "top_fields": guidance.get("top_fields") if isinstance(guidance.get("top_fields"), list) else [],
                "top_operators": guidance.get("top_operators") if isinstance(guidance.get("top_operators"), list) else [],
                "preferred_windows": guidance.get("preferred_windows") if isinstance(guidance.get("preferred_windows"), list) else [],
                "field_combinations": guidance.get("field_combinations") if isinstance(guidance.get("field_combinations"), list) else [],
                "risk_flags": guidance.get("risk_flags") if isinstance(guidance.get("risk_flags"), list) else [],
                "outcomes": outcomes,
                "score_adjustment_eligibility": scoring_eligibility,
                "assistant_guidance": guidance,
            }
        )
    return list(reversed(items))


def assistant_context_snapshot(
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_prompt: bool = True,
    include_sensitive: bool = False,
    load_config: LoadConfig,
    latest_result_snapshot: Snapshot,
    cloud_alpha_snapshot: Snapshot,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        memory = ResearchMemory(config.ops.storage_dir)
        memory_summary = memory.summary(limit=limit, top_n=top_n)
        memory_guidance = memory.generation_guidance(limit=limit, top_n=top_n, summary=memory_summary)
        latest = latest_result_snapshot()
        cloud = cloud_alpha_snapshot()
        return build_assistant_context_pack(
            config,
            latest_result_snapshot=latest,
            cloud_alpha_snapshot=cloud,
            memory_summary=memory_summary,
            memory_guidance=memory_guidance,
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_sensitive=include_sensitive,
        )
    except Exception as exc:
        return web_error(exc, "ASSISTANT_CONTEXT_ERROR")


def assistant_request_snapshot(
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_prompt: bool = True,
    include_offline_draft: bool = True,
    include_sensitive: bool = False,
    assistant_context_snapshot: Snapshot,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        context = assistant_context_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=True,
            include_sensitive=include_sensitive,
        )
        if context.get("ok") is False:
            return context
        return build_assistant_request_pack(
            context,
            include_prompt=include_prompt,
            include_offline_draft=include_offline_draft,
        )
    except Exception as exc:
        return web_error(exc, "ASSISTANT_REQUEST_ERROR")


def assistant_response_parse_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_output = str((payload or {}).get("raw_output") or (payload or {}).get("text") or "")
    if not raw_output.strip():
        raise AssistantResponseParseError("assistant response is empty")
    return parse_assistant_response(raw_output)


def assistant_response_guidance_payload(
    payload: dict[str, Any],
    *,
    bounded_query_float: BoundedFloat = _bounded_float,
) -> dict[str, Any]:
    raw_output = str((payload or {}).get("raw_output") or (payload or {}).get("text") or "")
    if not raw_output.strip():
        raise AssistantResponseParseError("assistant response is empty")
    min_confidence = bounded_query_float((payload or {}).get("min_confidence", 0.0), 0.0, 1.0)
    return assistant_response_to_generation_guidance(
        parse_assistant_response(raw_output),
        min_confidence=min_confidence,
    )


def save_assistant_guidance_payload(
    payload: dict[str, Any],
    *,
    run_config_from_payload: RunConfigFromPayload,
    bounded_query_float: BoundedFloat = _bounded_float,
    payload_truthy: PayloadTruthy = _payload_truthy,
    assistant_guidance_snapshot: Snapshot,
    repository_factory: Callable[[str], ResearchRepository] = ResearchRepository,
) -> dict[str, Any]:
    payload = dict(payload or {})
    run_config = run_config_from_payload(payload)
    min_confidence = bounded_query_float(
        payload.get(
            "min_confidence",
            payload.get("assistant_min_confidence", run_config.ops.budget.assistant_guidance_min_confidence),
        ),
        0.0,
        1.0,
    )
    supplied_guidance = payload.get("assistant_guidance")
    if isinstance(supplied_guidance, dict):
        guidance = dict(supplied_guidance)
        guidance.setdefault("source", "assistant_guidance_argument")
        guidance.setdefault("min_confidence", min_confidence)
        confidence = bounded_query_float(guidance.get("confidence", 1.0), 0.0, 1.0)
        if confidence < min_confidence:
            guidance["usable"] = False
            guidance["reason"] = "confidence_below_threshold"
        guidance = ensure_assistant_guidance_digest(guidance)
    else:
        raw_output = str(payload.get("assistant_response") or payload.get("raw_output") or payload.get("text") or "")
        if not raw_output.strip():
            raise AssistantResponseParseError("assistant response is empty")
        guidance = assistant_response_to_generation_guidance(
            parse_assistant_response(raw_output),
            min_confidence=min_confidence,
        )
        if not payload_truthy(guidance.get("usable", True)):
            guidance["reason"] = "confidence_below_threshold"

    usable = guidance.get("ok") is not False and payload_truthy(guidance.get("usable", True))
    has_bias = bool(
        guidance.get("top_fields")
        or guidance.get("top_operators")
        or guidance.get("preferred_windows")
        or guidance.get("field_combinations")
    )
    if not usable:
        return {
            "ok": True,
            "saved": False,
            "reason": guidance.get("reason") or "not_usable",
            "assistant_guidance": guidance,
            "snapshot": assistant_guidance_snapshot(min_confidence=min_confidence),
        }
    if not has_bias:
        return {
            "ok": True,
            "saved": False,
            "reason": "no_generator_bias",
            "assistant_guidance": guidance,
            "snapshot": assistant_guidance_snapshot(min_confidence=min_confidence),
        }

    repository_factory(run_config.ops.storage_dir).save_assistant_guidance(
        guidance,
        source=str(payload.get("source") or "web_save_assistant_guidance"),
    )
    return {
        "ok": True,
        "saved": True,
        "assistant_guidance": guidance,
        "snapshot": assistant_guidance_snapshot(min_confidence=min_confidence),
    }


__all__ = [
    # Module-level
    "logger",
    # Type aliases
    "LoadConfig",
    "WebError",
    "BoundedFloat",
    "PayloadTruthy",
    "ReadStorageJsonl",
    "StoragePath",
    "SafeErrorMessage",
    "RunConfigFromPayload",
    "Snapshot",
    # Research snapshots
    "research_memory_snapshot",
    "research_knowledge_snapshot",
    "prompt_run_ledger_snapshot",
    "research_observability_snapshot",
    "durable_job_rows",
    # Assistant guidance
    "assistant_guidance_snapshot",
    "assistant_guidance_history",
    # Assistant payloads
    "assistant_context_snapshot",
    "assistant_request_snapshot",
    "assistant_response_parse_payload",
    "assistant_response_guidance_payload",
    "save_assistant_guidance_payload",
    # Run history & profile
    "latest_result_snapshot",
    "latest_run_history_path",
    "user_profile_snapshot",
]
