"""Assistant request pack and prompt rendering.

Contains ``build_assistant_request_pack`` (the provider-neutral LLM request
envelope), ``render_assistant_request_prompt``, and the supporting prompt
diagnostics / budgeting helpers.
"""

from __future__ import annotations

import json
from typing import Any

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.research.context import render_context_prompt
from brain_alpha_ops.research.prompt_templates import load_system_prompt

from ._constants import (
    ASSISTANT_REQUEST_SCHEMA_VERSION,
    ASSISTANT_RESPONSE_SCHEMA,
    DEFAULT_MAX_PROMPT_TOKENS,
    INTERNAL_CONTEXT_METADATA_KEYS,
)
from ._helpers import _as_dict, _digest_json, _digest_text, _unique_strings
from .offline import build_offline_assistant_response


def build_assistant_request_pack(
    context_pack: dict[str, Any],
    *,
    include_prompt: bool = True,
    include_offline_draft: bool = True,
    max_prompt_tokens: int = DEFAULT_MAX_PROMPT_TOKENS,
) -> dict[str, Any]:
    """Build a provider-neutral LLM request envelope from a context pack."""
    original_context = _strip_internal_context_metadata(dict(context_pack or {}))
    context = _budgeted_context(original_context, max_prompt_tokens=max_prompt_tokens)
    prompt = render_assistant_request_prompt(context)
    context_payload = _strip_internal_context_metadata(dict(context))
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
                {"role": "system", "content": load_system_prompt()},
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


def _strip_internal_context_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_internal_context_metadata(item)
            for key, item in value.items()
            if str(key) not in INTERNAL_CONTEXT_METADATA_KEYS
        }
    if isinstance(value, list):
        return [_strip_internal_context_metadata(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_internal_context_metadata(item) for item in value)
    return value


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


def _assistant_prompt_diagnostics(context: dict[str, Any], prompt: str) -> dict[str, Any]:
    context_diagnostics = _as_dict(context.get("prompt_diagnostics"))
    prompt_budget = _as_dict(context.get("prompt_budget"))
    focus = _as_dict(context.get("generation_focus"))
    observability = _as_dict(context.get("observability"))
    latest = _as_dict(context.get("latest_result"))
    robustness = _as_dict(context.get("robustness"))
    risk_flags = _unique_strings(
        list(context_diagnostics.get("risk_flags") or [])
        + list(observability.get("warning_flags") or [])
        + list(observability.get("blocking_flags") or [])
        + list(robustness.get("risk_flags") or [])
    )
    anti = _as_dict(robustness.get("anti_overfit"))
    rolling = _as_dict(robustness.get("rolling_validation"))
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
        "anti_overfit_available_count": int(anti.get("available_count") or 0),
        "rolling_validation_available_count": int(rolling.get("available_count") or 0),
        "evidence_digest": context_diagnostics.get("evidence_digest") or _digest_json(
            {
                "focus": focus,
                "risk_flags": risk_flags,
                "observability": observability,
                "robustness": robustness,
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
