"""Stable identifiers for assistant generation guidance."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


_DIGEST_KEYS = (
    "schema_version",
    "summary",
    "confidence",
    "sample_size",
    "top_fields",
    "top_operators",
    "preferred_windows",
    "field_combinations",
    "avoid_patterns",
    "risk_flags",
    "recommended_next_actions",
    "operational_flags",
)


def assistant_guidance_digest(guidance: dict[str, Any] | None) -> str:
    """Return a short stable digest for generator-relevant guidance content."""
    row = guidance or {}
    canonical = {key: row.get(key) for key in _DIGEST_KEYS if key in row}
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, default=str)
    return "ag_" + sha256(encoded.encode("utf-8")).hexdigest()[:16]


def ensure_assistant_guidance_digest(guidance: dict[str, Any] | None) -> dict[str, Any]:
    """Return a shallow copy with ``guidance_digest`` populated."""
    row = dict(guidance or {})
    digest = str(row.get("guidance_digest") or row.get("assistant_guidance_digest") or "").strip()
    row["guidance_digest"] = digest or assistant_guidance_digest(row)
    return row


def assistant_guidance_candidate_metadata(guidance: dict[str, Any] | None) -> dict[str, Any]:
    """Return candidate submission metadata for applied assistant guidance."""
    row = ensure_assistant_guidance_digest(guidance)
    metadata: dict[str, Any] = {
        "assistant_guidance_digest": row.get("guidance_digest", ""),
        "assistant_guidance_source": row.get("source") or row.get("persistence_source") or "",
        "assistant_guidance_confidence": row.get("confidence"),
    }
    outcome = _outcome_dict(row)
    status = str(
        row.get("historical_outcome_status")
        or row.get("assistant_guidance_outcome_status")
        or _outcome_status(outcome)
        or ""
    ).strip()
    if status:
        metadata["assistant_guidance_outcome_status"] = status
    if outcome:
        metadata["assistant_guidance_outcome"] = outcome
        for key in ("count", "success_count", "success_rate", "avg_score", "avg_sharpe", "avg_fitness"):
            if key in outcome:
                metadata[f"assistant_guidance_outcome_{key}"] = outcome.get(key)
    return metadata


def assistant_guidance_outcome_status(outcome: dict[str, Any] | None) -> str:
    """Classify historical assistant-guidance outcomes for reuse/scoring."""
    return _outcome_status(outcome or {})


def assistant_guidance_scoring_policy(scoring: Any) -> dict[str, Any]:
    """Return the score-adjustment policy exposed by ``ScoringConfig``."""
    return {
        "enabled": bool(getattr(scoring, "assistant_guidance_score_adjustment_enabled", True)),
        "min_confidence": _clamp(
            _float_value(getattr(scoring, "assistant_guidance_score_min_confidence", 0.6)),
            0.0,
            1.0,
        ),
        "min_outcome_count": max(0, _int_value(getattr(scoring, "assistant_guidance_score_min_outcome_count", 1))),
        "bonus_cap": max(0.0, _float_value(getattr(scoring, "assistant_guidance_score_bonus_cap", 4.0))),
        "penalty_cap": max(0.0, _float_value(getattr(scoring, "assistant_guidance_score_penalty_cap", 5.0))),
        "applies_to": "local_prior_score_only",
    }


def assistant_guidance_scoring_eligibility(
    guidance: dict[str, Any] | None,
    outcome: dict[str, Any] | None,
    policy: dict[str, Any] | None,
) -> dict[str, Any]:
    """Explain whether guidance may influence local ranking adjustments."""
    guidance = guidance if isinstance(guidance, dict) else {}
    outcome = outcome if isinstance(outcome, dict) else {}
    policy = policy if isinstance(policy, dict) else {}
    enabled = bool(policy.get("enabled", True))
    confidence = _confidence_value(guidance.get("confidence", 1.0))
    min_confidence = _clamp(_float_value(policy.get("min_confidence", 0.6)), 0.0, 1.0)
    outcome_count = _int_value(outcome.get("count"))
    min_outcome_count = max(0, _int_value(policy.get("min_outcome_count", 1)))
    outcome_status = assistant_guidance_outcome_status(outcome)
    digest = str(guidance.get("guidance_digest") or outcome.get("guidance_digest") or "").strip()
    if not enabled:
        eligible = False
        reason = "assistant guidance score adjustment is disabled"
    elif not digest:
        eligible = False
        reason = "guidance digest is missing"
    elif guidance.get("usable") is False:
        eligible = False
        reason = "guidance is not usable for generation"
    elif confidence < min_confidence:
        eligible = False
        reason = "guidance confidence is below scoring policy"
    elif outcome_count < min_outcome_count:
        eligible = False
        reason = "not enough historical outcome samples"
    else:
        eligible = True
        reason = "eligible for local ranking adjustment"
    return {
        "eligible": eligible,
        "reason": reason,
        "guidance_digest": digest,
        "confidence": confidence,
        "min_confidence": min_confidence,
        "outcome_count": outcome_count,
        "min_outcome_count": min_outcome_count,
        "outcome_status": outcome_status,
        "adjustment_direction": _adjustment_direction(outcome_status) if eligible else "none",
    }


def _outcome_dict(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("historical_outcome")
    if not isinstance(raw, dict):
        raw = row.get("assistant_guidance_outcome")
    if not isinstance(raw, dict):
        return {}
    outcome: dict[str, Any] = {}
    for key in (
        "guidance_digest",
        "count",
        "success_count",
        "success_rate",
        "avg_score",
        "avg_sharpe",
        "avg_fitness",
        "pass_fail",
    ):
        value = raw.get(key)
        if value not in (None, ""):
            outcome[key] = value
    return outcome


def _outcome_status(outcome: dict[str, Any]) -> str:
    if not outcome:
        return ""
    count = _int_value(outcome.get("count"))
    if count <= 0:
        return "unknown"
    success_rate = _float_value(outcome.get("success_rate"))
    avg_score = _float_value(outcome.get("avg_score"))
    if count >= 2 and (success_rate <= 0.25 or avg_score <= 50):
        return "weak"
    if success_rate >= 0.5 or avg_score >= 70:
        return "strong"
    return "neutral"


def _int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _confidence_value(value: Any) -> float:
    confidence = _float_value(value)
    if confidence > 1.0:
        confidence = confidence / 100.0
    return _clamp(confidence, 0.0, 1.0)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _adjustment_direction(status: str) -> str:
    if status == "strong":
        return "bonus"
    if status == "weak":
        return "penalty"
    if status == "neutral":
        return "small_bonus"
    return "none"
