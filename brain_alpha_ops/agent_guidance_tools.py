"""Assistant-guidance helpers used by the agent tool facade."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.guidance import assistant_guidance_candidate_metadata, ensure_assistant_guidance_digest


def has_generator_bias(guidance: dict[str, Any] | None) -> bool:
    """Return True when guidance contains bias keys that the generator applies.

    Covers both the keys that ``assistant_guidance_for_generator`` consumes
    (top_operators, preferred_windows, field_combinations, top_fields) and
    any raw guidance key that directly biases generation.
    """
    if not guidance:
        return False
    return bool(
        guidance.get("top_operators")
        or guidance.get("preferred_windows")
        or guidance.get("field_combinations")
        or guidance.get("top_fields")
    )


def assistant_guidance_for_generator(guidance: dict[str, Any]) -> dict[str, Any]:
    if guidance.get("ok") is False or not _truthy(guidance.get("usable", True)):
        return {}

    top_operators = _unique_text_items(guidance.get("top_operators"))
    preferred_windows = _unique_number_items(guidance.get("preferred_windows"))
    field_combinations = _field_combinations(guidance.get("field_combinations"))
    top_fields = _unique_text_items(guidance.get("top_fields"))
    if top_fields:
        field_combinations.append({"fields": top_fields, "rationale": "assistant top fields"})
        field_combinations = _unique_field_combinations(field_combinations)

    if not top_operators and not preferred_windows and not field_combinations:
        return {}

    return {
        "sample_size": max(3, _safe_int(guidance.get("sample_size"), 0)),
        "top_operators": top_operators,
        "preferred_windows": preferred_windows,
        "field_combinations": field_combinations,
    }


def merge_generation_guidance(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_size": max(
            3,
            _safe_int(base.get("sample_size"), 0) + _safe_int(overlay.get("sample_size"), 0),
        ),
        "top_operators": _unique_text_items(
            _text_items(base.get("top_operators")) + _text_items(overlay.get("top_operators"))
        ),
        "preferred_windows": _unique_number_items(
            _number_items(base.get("preferred_windows")) + _number_items(overlay.get("preferred_windows"))
        ),
        "field_combinations": _unique_field_combinations(
            _field_combinations(base.get("field_combinations")) + _field_combinations(overlay.get("field_combinations"))
        ),
    }


def assistant_guidance_summary(guidance: dict[str, Any], *, applied: bool) -> dict[str, Any]:
    guidance = ensure_assistant_guidance_digest(guidance)
    metadata = assistant_guidance_candidate_metadata(guidance)
    usable = guidance.get("ok") is not False and _truthy(guidance.get("usable", True))
    if applied:
        reason = "applied_to_generator"
    elif not usable:
        reason = "not_usable"
    else:
        reason = "no_generator_bias"
    return {
        "ok": guidance.get("ok", True),
        "source": guidance.get("source", ""),
        "usable": usable,
        "applied": applied,
        "reason": reason,
        "guidance_digest": guidance.get("guidance_digest"),
        "confidence": guidance.get("confidence"),
        "min_confidence": guidance.get("min_confidence"),
        "sample_size": guidance.get("sample_size"),
        "top_fields": _unique_text_items(guidance.get("top_fields"))[:10],
        "top_operators": _unique_text_items(guidance.get("top_operators"))[:10],
        "preferred_windows": _unique_number_items(guidance.get("preferred_windows"))[:10],
        "field_combinations": _field_combinations(guidance.get("field_combinations"))[:10],
        "field_combinations_count": len(_field_combinations(guidance.get("field_combinations"))),
        "risk_flags": _unique_text_items(guidance.get("risk_flags"))[:10],
        "operational_flags": guidance.get("operational_flags") if isinstance(guidance.get("operational_flags"), dict) else {},
        "historical_outcome_status": metadata.get("assistant_guidance_outcome_status", "unknown"),
        "historical_outcome": metadata.get("assistant_guidance_outcome", {}),
    }


def attach_assistant_guidance(candidate: Candidate, guidance: dict[str, Any]) -> None:
    guidance = ensure_assistant_guidance_digest(guidance)
    digest = str(guidance.get("guidance_digest") or "")
    tags = list(candidate.source_tags or [])
    for tag in ("assistant_guided", f"assistant_guidance_{digest}"):
        if tag and tag not in tags:
            tags.append(tag)
    candidate.source_tags = tags
    submission = dict(candidate.submission or {})
    submission.update(assistant_guidance_candidate_metadata(guidance))
    candidate.submission = submission


def guidance_sample_size(guidance: dict[str, Any]) -> int:
    return max(
        len(_text_items(guidance.get("top_fields"))),
        len(_text_items(guidance.get("top_operators"))),
        len(_number_items(guidance.get("preferred_windows"))),
        len(_field_combinations(guidance.get("field_combinations"))),
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _text_items(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _unique_text_items(value: Any) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in _text_items(value):
        marker = item.lower()
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def _number_items(value: Any) -> list[int | float]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    rows: list[int | float] = []
    for item in values:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if number != number or number in (float("inf"), float("-inf")):
            continue
        rows.append(int(number) if number.is_integer() else number)
    return rows


def _unique_number_items(value: Any) -> list[int | float]:
    seen: set[float] = set()
    unique: list[int | float] = []
    for item in _number_items(value):
        marker = float(item)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def _field_combinations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            fields = _unique_text_items(item.get("fields") or item.get("field") or item.get("value"))
            rationale = str(item.get("rationale") or "")
        else:
            fields = _unique_text_items(item)
            rationale = ""
        if fields:
            rows.append({"fields": fields, "rationale": rationale})
    return rows


def _unique_field_combinations(value: Any) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    unique: list[dict[str, Any]] = []
    for combo in _field_combinations(value):
        fields = _unique_text_items(combo.get("fields"))
        marker = tuple(field.lower() for field in fields)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        unique.append({"fields": fields, "rationale": str(combo.get("rationale") or "")})
    return unique


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
