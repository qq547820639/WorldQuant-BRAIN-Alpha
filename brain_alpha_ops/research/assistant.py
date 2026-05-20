"""Assistant request and response helpers.

This module turns the read-only assistant context pack into a provider-neutral
LLM request envelope. It also provides a deterministic offline draft so the
project remains useful when no external model client is configured.
"""

from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Any

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.research.context import render_context_prompt
from brain_alpha_ops.research.guidance import assistant_guidance_digest


ASSISTANT_REQUEST_SCHEMA_VERSION = "assistant_request_pack.v1"
ASSISTANT_RESPONSE_SCHEMA_VERSION = "assistant_response.v1"
ASSISTANT_GUIDANCE_SCHEMA_VERSION = "assistant_generation_guidance.v1"
DEFAULT_MAX_PROMPT_TOKENS = 6000

SYSTEM_PROMPT = (
    "You are a quantitative investment research assistant for WorldQuant BRAIN FASTEXPR. "
    "Use only the supplied local context. Return one valid JSON object only; no markdown."
)

ASSISTANT_RESPONSE_SCHEMA: dict[str, Any] = {
    "schema_version": ASSISTANT_RESPONSE_SCHEMA_VERSION,
    "type": "object",
    "required": [
        "summary",
        "recommended_next_actions",
        "risk_flags",
        "candidate_adjustments",
        "follow_up_questions",
        "confidence",
    ],
    "properties": {
        "summary": {"type": "string"},
        "recommended_next_actions": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "candidate_adjustments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["target", "value", "rationale"],
                "properties": {
                    "target": {"type": "string"},
                    "value": {"type": ["string", "number", "array", "object", "boolean", "null"]},
                    "rationale": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {"type": "object"},
    },
    "additionalProperties": True,
}


class AssistantResponseParseError(ValueError):
    """Raised when an assistant response cannot be parsed as useful JSON."""


def build_assistant_request_pack(
    context_pack: dict[str, Any],
    *,
    include_prompt: bool = True,
    include_offline_draft: bool = True,
    max_prompt_tokens: int = DEFAULT_MAX_PROMPT_TOKENS,
) -> dict[str, Any]:
    """Build a provider-neutral LLM request envelope from a context pack."""
    original_context = dict(context_pack or {})
    context = _budgeted_context(original_context, max_prompt_tokens=max_prompt_tokens)
    prompt = render_assistant_request_prompt(context)
    context_payload = dict(context)
    context_payload.pop("prompt", None)
    prompt_diagnostics = _assistant_prompt_diagnostics(context_payload, prompt)
    payload: dict[str, Any] = {
        "ok": True,
        "schema_version": ASSISTANT_REQUEST_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source": "assistant_context_pack",
        "context_schema_version": context.get("schema_version", ""),
        "context_digest": _digest_json(context_payload),
        "prompt_digest": _digest_text(prompt),
        "prompt_diagnostics": prompt_diagnostics,
        "request": {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_schema": ASSISTANT_RESPONSE_SCHEMA,
            "model_hints": {
                "temperature": 0.2,
                "max_output_tokens": 1600,
                "response_format": "json_object",
                "prompt_budget": {
                    "estimated_prompt_tokens": prompt_diagnostics["estimated_prompt_tokens"],
                    "estimated_context_tokens": prompt_diagnostics["estimated_context_tokens"],
                    "max_prompt_tokens": prompt_diagnostics["max_prompt_tokens"],
                    "max_output_tokens": 1600,
                    "budget_applied": prompt_diagnostics["budget_applied"],
                    "truncated_sections": prompt_diagnostics["truncated_sections"],
                },
                "review_roles": [
                    "generator_advisor",
                    "risk_reviewer",
                    "expression_novelty_reviewer",
                ],
            },
        },
        "context_pack": context_payload,
        "review_chain": [
            {
                "role": "generator_advisor",
                "focus": "candidate fields, operators, windows, and hypothesis diversity",
            },
            {
                "role": "risk_reviewer",
                "focus": "stale cloud cache, pending official work, backtest failure pressure, and submission guardrails",
            },
            {
                "role": "expression_novelty_reviewer",
                "focus": "duplicate expression fingerprints, micro-variants, and correlation-sensitive reuse",
            },
        ],
    }
    if include_prompt:
        payload["prompt"] = prompt
    if include_offline_draft:
        payload["offline_draft"] = build_offline_assistant_response(original_context)
    return payload


def render_assistant_request_prompt(context_pack: dict[str, Any]) -> str:
    """Render the user message that should be sent with ``SYSTEM_PROMPT``."""
    context_prompt = str(context_pack.get("prompt") or render_context_prompt(context_pack)).strip()
    schema_text = json.dumps(ASSISTANT_RESPONSE_SCHEMA, ensure_ascii=False, indent=2, default=str)
    lines = [
        context_prompt,
        "",
        "Return one JSON object only. Do not include markdown, prose outside JSON, or code fences.",
        "Ground every recommendation in the supplied context. Do not invent metrics, alpha ids, fields, or official results.",
        "Prefer local evidence, avoid duplicate micro-variants, and call out stale cloud cache or pending backtests when relevant.",
        "Use this response schema:",
        schema_text,
    ]
    return "\n".join(lines).strip() + "\n"


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

    actions = _unique_strings(context.get("recommended_next_actions") or [])
    actions.extend(observability_actions)
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
        },
    }


def parse_assistant_response(raw_output: str) -> dict[str, Any]:
    """Extract and normalize a JSON assistant response."""
    payload = _extract_json_payload(raw_output)
    if not isinstance(payload, dict):
        raise AssistantResponseParseError("assistant response must be a JSON object")
    return _normalize_assistant_response(payload)


def assistant_response_to_generation_guidance(
    assistant_response: dict[str, Any],
    *,
    min_confidence: float = 0.0,
) -> dict[str, Any]:
    """Convert a normalized assistant response into generator-ready guidance."""
    response = _normalize_assistant_response(assistant_response)
    confidence = float(response.get("confidence") or 0.0)
    usable = confidence >= _clamp(float(min_confidence or 0.0), 0.0, 1.0)

    fields: list[str] = []
    operators: list[str] = []
    windows: list[int | float] = []
    field_combinations: list[dict[str, Any]] = []
    avoid_patterns: list[dict[str, str]] = []
    raw_adjustments = response.get("candidate_adjustments") or []

    for item in raw_adjustments:
        adjustment = _as_dict(item)
        target = str(adjustment.get("target") or "").strip().lower()
        value = adjustment.get("value")
        rationale = str(adjustment.get("rationale") or "")
        if target in {"field", "fields", "top_fields", "data_fields"}:
            fields.extend(_string_items(value))
        elif target in {"operator", "operators", "top_operators"}:
            operators.extend(_string_items(value))
        elif target in {"window", "windows", "lookback", "lookbacks", "preferred_windows"}:
            windows.extend(_number_items(value if isinstance(value, list) else [value]))
        elif target in {"field_combination", "field_combinations", "combo", "combination"}:
            combo_fields = _string_items(value)
            if combo_fields:
                field_combinations.append({"fields": combo_fields, "rationale": rationale})
        elif target in {"avoid", "avoid_pattern", "failure_mode", "risk"}:
            avoid_patterns.append({"target": target or "avoid", "value": str(value), "rationale": rationale})

    actions = response.get("recommended_next_actions") or []
    risk_flags = response.get("risk_flags") or []
    should_refresh_cloud = any("cloud" in item.lower() and ("stale" in item.lower() or "refresh" in item.lower() or "sync" in item.lower()) for item in actions + risk_flags)
    should_wait_backtests = any("pending" in item.lower() or "backtest" in item.lower() for item in actions + risk_flags)
    submit_blocked = any("submit" in item.lower() and ("confirm" in item.lower() or "required" in item.lower()) for item in risk_flags)

    payload = {
        "ok": True,
        "schema_version": ASSISTANT_GUIDANCE_SCHEMA_VERSION,
        "source": response.get("source") or "assistant_response",
        "usable": usable,
        "confidence": confidence,
        "min_confidence": _clamp(float(min_confidence or 0.0), 0.0, 1.0),
        "sample_size": len(raw_adjustments),
        "top_fields": _unique_strings(fields),
        "top_operators": _unique_strings(operators),
        "preferred_windows": _unique_numbers(windows),
        "field_combinations": field_combinations,
        "avoid_patterns": avoid_patterns,
        "risk_flags": list(risk_flags),
        "recommended_next_actions": list(actions),
        "operational_flags": {
            "refresh_cloud_before_submit": should_refresh_cloud,
            "wait_for_pending_backtests": should_wait_backtests,
            "submit_requires_confirmation": submit_blocked,
        },
        "summary": response.get("summary") or "",
    }
    payload["guidance_digest"] = assistant_guidance_digest(payload)
    return payload


def _normalize_assistant_response(payload: dict[str, Any]) -> dict[str, Any]:
    summary = str(payload.get("summary") or payload.get("answer") or payload.get("analysis") or "").strip()
    if not summary:
        raise AssistantResponseParseError("assistant response missing summary")
    return {
        "ok": True,
        "schema_version": str(payload.get("schema_version") or ASSISTANT_RESPONSE_SCHEMA_VERSION),
        "source": str(payload.get("source") or "assistant_model"),
        "summary": summary,
        "recommended_next_actions": _unique_strings(
            payload.get("recommended_next_actions")
            or payload.get("next_actions")
            or payload.get("actions")
            or []
        ),
        "risk_flags": _unique_strings(payload.get("risk_flags") or payload.get("risks") or []),
        "candidate_adjustments": _normalize_adjustments(
            payload.get("candidate_adjustments")
            or payload.get("mutations")
            or payload.get("ideas")
            or []
        ),
        "follow_up_questions": _unique_strings(
            payload.get("follow_up_questions")
            or payload.get("questions")
            or payload.get("open_questions")
            or []
        ),
        "confidence": _normalize_confidence(payload.get("confidence", payload.get("confidence_score"))),
        "evidence": _as_dict(payload.get("evidence")),
    }


def _assistant_prompt_diagnostics(context: dict[str, Any], prompt: str) -> dict[str, Any]:
    context_diagnostics = _as_dict(context.get("prompt_diagnostics"))
    prompt_budget = _as_dict(context.get("prompt_budget"))
    focus = _as_dict(context.get("generation_focus"))
    observability = _as_dict(context.get("observability"))
    latest = _as_dict(context.get("latest_result"))
    risk_flags = _unique_strings(
        list(context_diagnostics.get("risk_flags") or [])
        + list(observability.get("warning_flags") or [])
        + list(observability.get("blocking_flags") or [])
    )
    prompt_tokens = max(1, len(str(prompt or "")) // 4)
    return {
        "schema_version": "assistant_request_prompt_diagnostics.v1",
        "context_schema_version": context.get("schema_version", ""),
        "estimated_context_tokens": int(context_diagnostics.get("estimated_context_tokens") or max(1, len(json.dumps(context, ensure_ascii=False, default=str)) // 4)),
        "estimated_prompt_tokens": prompt_tokens,
        "max_prompt_tokens": int(prompt_budget.get("max_prompt_tokens") or DEFAULT_MAX_PROMPT_TOKENS),
        "budget_applied": bool(prompt_budget.get("budget_applied")),
        "truncated_sections": list(prompt_budget.get("truncated_sections") or []),
        "prompt_line_count": len(str(prompt or "").splitlines()),
        "duplicate_focus_count": int(context_diagnostics.get("duplicate_focus_count") or len(focus.get("duplicate_expressions") or [])),
        "risk_flags": risk_flags[:10],
        "observability_risk_level": str(observability.get("risk_level") or "unknown"),
        "pending_backtest_count": int(latest.get("pending_backtest_count") or 0),
        "evidence_digest": context_diagnostics.get("evidence_digest") or _digest_json(
            {
                "focus": focus,
                "risk_flags": risk_flags,
                "observability": observability,
            }
        )[:12],
    }


def _budgeted_context(context: dict[str, Any], *, max_prompt_tokens: int) -> dict[str, Any]:
    safe_max = max(1200, int(max_prompt_tokens or DEFAULT_MAX_PROMPT_TOKENS))
    prompt = render_assistant_request_prompt(context)
    if _estimated_tokens(prompt) <= safe_max:
        return {
            **context,
            "prompt_budget": {
                "schema_version": "assistant_prompt_budget.v1",
                "max_prompt_tokens": safe_max,
                "estimated_prompt_tokens_before": _estimated_tokens(prompt),
                "budget_applied": False,
                "truncated_sections": [],
            },
        }

    compact = _compact_context_lists(context, list_limit=3)
    compact.pop("prompt", None)
    compact_prompt = render_assistant_request_prompt(compact)
    compact["prompt_budget"] = {
        "schema_version": "assistant_prompt_budget.v1",
        "max_prompt_tokens": safe_max,
        "estimated_prompt_tokens_before": _estimated_tokens(prompt),
        "estimated_prompt_tokens_after": _estimated_tokens(compact_prompt),
        "budget_applied": True,
        "truncated_sections": [
            "latest_result.top_candidates",
            "latest_result.pending_backtests",
            "latest_result.passed_candidates",
            "latest_result.backtest_slots",
            "latest_result.backtest_records",
            "cloud_alphas.sample_alphas",
            "research_memory.*",
            "expression_index.*",
            "generation_focus.*",
            "observability.*",
        ],
    }
    return compact


def _compact_context_lists(value: Any, *, list_limit: int) -> Any:
    if isinstance(value, list):
        return [_compact_context_lists(item, list_limit=list_limit) for item in value[:list_limit]]
    if isinstance(value, dict):
        return {key: _compact_context_lists(item, list_limit=list_limit) for key, item in value.items()}
    return value


def _estimated_tokens(text: str) -> int:
    return max(1, len(str(text or "")) // 4)


def _extract_json_payload(raw_output: str) -> Any:
    raw = str(raw_output or "").strip()
    if not raw:
        raise AssistantResponseParseError("assistant response is empty")
    if raw.startswith(("{", "[")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    for pattern in (r"(\{.*\})", r"(\[.*\])"):
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    raise AssistantResponseParseError(f"cannot extract valid JSON from assistant response: {raw[:200]}")


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


def _normalize_adjustments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            target = str(item.get("target") or item.get("focus") or item.get("field") or f"item_{index + 1}")
            item_value = item.get("value", item.get("proposal", item.get("detail", "")))
            rationale = str(item.get("rationale") or item.get("reason") or item.get("why") or "")
        else:
            target = "general"
            item_value = str(item)
            rationale = ""
        rows.append({"target": target, "value": item_value, "rationale": rationale})
    return rows


def _unique_strings(value: Any) -> list[str]:
    rows = _string_items(value)
    seen: set[str] = set()
    unique: list[str] = []
    for item in rows:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _string_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _number_items(value: Any) -> list[int | float]:
    items = value if isinstance(value, list) else []
    rows: list[int | float] = []
    for item in items:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        rows.append(int(number) if number.is_integer() else number)
    return rows


def _unique_numbers(value: Any) -> list[int | float]:
    rows = _number_items(value) if not isinstance(value, list) else [item for item in value if isinstance(item, (int, float))]
    unique: list[int | float] = []
    seen: set[float] = set()
    for item in rows:
        marker = float(item)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(int(marker) if marker.is_integer() else marker)
    return unique


def _normalize_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    if not math.isfinite(number):
        return 0.5
    if 1.0 < number <= 100.0:
        number = number / 100.0
    return round(_clamp(number, 0.0, 1.0), 2)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _guidance_outcomes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        row = _as_dict(item)
        digest = str(row.get("guidance_digest") or "").strip()
        if not digest:
            continue
        rows.append({
            "guidance_digest": digest,
            "count": _int_value(row.get("count")),
            "success_count": _int_value(row.get("success_count")),
            "success_rate": _float_value(row.get("success_rate")),
            "avg_score": _float_value(row.get("avg_score")),
            "avg_sharpe": _float_value(row.get("avg_sharpe")),
            "avg_fitness": _float_value(row.get("avg_fitness")),
        })
    return rows


def _strong_guidance_outcome(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    for row in outcomes:
        if _guidance_count(row) <= 0:
            continue
        if _guidance_success_rate(row) >= 0.5 or _float_value(row.get("avg_score")) >= 70:
            return row
    return {}


def _weak_guidance_outcome(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    for row in outcomes:
        count = _guidance_count(row)
        if count <= 0:
            continue
        success_rate = _guidance_success_rate(row)
        avg_score = _float_value(row.get("avg_score"))
        if (count >= 2 and success_rate <= 0.25) or (success_rate == 0.0 and avg_score <= 50):
            return row
    return {}


def _duplicate_expressions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        row = _as_dict(item)
        if not row:
            continue
        try:
            count = int(row.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 1:
            rows.append(row)
    return rows


def _recent_backtest_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_as_dict(item) for item in value[-10:] if _as_dict(item)]


def _guidance_digest(row: dict[str, Any] | None) -> str:
    return str((row or {}).get("guidance_digest") or "")


def _guidance_count(row: dict[str, Any] | None) -> int:
    return _int_value((row or {}).get("count"))


def _guidance_success_rate(row: dict[str, Any] | None) -> float:
    return _float_value((row or {}).get("success_rate"))


def _int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return round(number, 4)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _digest_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return _digest_text(encoded)
