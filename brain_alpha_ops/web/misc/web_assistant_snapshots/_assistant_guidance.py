"""Assistant guidance snapshot and history builders."""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.research.guidance import (
    assistant_guidance_outcome_status,
    assistant_guidance_scoring_eligibility,
    assistant_guidance_scoring_policy,
    ensure_assistant_guidance_digest,
)
from brain_alpha_ops.research.memory import ResearchMemory

from ._helpers import (
    BoundedFloat,
    LoadConfig,
    PayloadTruthy,
    ReadStorageJsonl,
    Snapshot,
    WebError,
    _bounded_float,
    _default_web_error,
    _payload_truthy,
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
