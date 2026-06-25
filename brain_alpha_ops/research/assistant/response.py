"""Assistant response parsing and generation-guidance conversion.

Contains ``parse_assistant_response``, ``assistant_response_to_generation_guidance``,
``_normalize_assistant_response``, and ``_normalize_adjustments``.
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research.assistant_json import AssistantResponseParseError
from brain_alpha_ops.research.assistant_json import (
    extract_json_payload as _extract_json_payload,
)
from brain_alpha_ops.research.guidance import assistant_guidance_digest

from ._constants import ASSISTANT_GUIDANCE_SCHEMA_VERSION, ASSISTANT_RESPONSE_SCHEMA_VERSION
from ._helpers import (
    _as_dict,
    _clamp,
    _normalize_confidence,
    _number_items,
    _string_items,
    _unique_numbers,
    _unique_strings,
)


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
