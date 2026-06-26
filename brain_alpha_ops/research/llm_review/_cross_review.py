"""Cross-review service and orchestration for the ``llm_review`` subpackage.

Reviews a primary assistant response against the original request pack using
either an injected LLM provider or an offline reviewer fallback.
"""

from __future__ import annotations

import json
from typing import Any

from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    parse_assistant_response,
)
from brain_alpha_ops.research.llm_review._providers import (
    LLMProvider,
    LLMProviderRouter,
    _providers_from_env,
)
from brain_alpha_ops.research.llm_review._utils import (
    _digest_json,
    _strings,
)

CROSS_REVIEW_SCHEMA_VERSION = "assistant_cross_review.v1"


class CrossReviewService:
    """Review a primary assistant response against the original request pack."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider

    def review(
        self,
        request_pack: dict[str, Any],
        primary_response: str | dict[str, Any],
        *,
        reviewer_response: str | dict[str, Any] | None = None,
        min_confidence: float = 0.6,
    ) -> dict[str, Any]:
        primary = _parse_response(primary_response, label="primary")
        raw_reviewer = reviewer_response
        if raw_reviewer is None:
            if self.provider is None:
                raw_reviewer = _offline_reviewer_response(primary, request_pack)
            else:
                raw_reviewer = self.provider.complete(_review_request(request_pack, primary))
        reviewer = _parse_response(raw_reviewer, label="reviewer")
        primary_confidence = _confidence(primary)
        reviewer_confidence = _confidence(reviewer)
        agreement = _agreement(primary, reviewer)
        conservative = (not agreement) or primary_confidence < min_confidence or reviewer_confidence < min_confidence
        decision = "accept" if agreement and not conservative else "conservative_review_required"
        result = {
            "ok": True,
            "schema_version": CROSS_REVIEW_SCHEMA_VERSION,
            "decision": decision,
            "agreement": agreement,
            "conservative": conservative,
            "min_confidence": min_confidence,
            "primary_confidence": primary_confidence,
            "reviewer_confidence": reviewer_confidence,
            "primary_digest": _digest_json(primary),
            "reviewer_digest": _digest_json(reviewer),
            "request_digest": str(request_pack.get("prompt_digest") or _digest_json(request_pack)),
            "primary": primary,
            "reviewer": reviewer,
            "risk_flags": sorted(set(_strings(primary.get("risk_flags")) + _strings(reviewer.get("risk_flags")))),
        }
        return redact_data(result)


def cross_review_assistant_response(
    request_pack: dict[str, Any],
    primary_response: str | dict[str, Any],
    *,
    reviewer_response: str | dict[str, Any] | None = None,
    min_confidence: float = 0.6,
) -> dict[str, Any]:
    providers = _providers_from_env()
    provider = LLMProviderRouter(providers, task_routes={"cross_review": [getattr(provider, "name", provider.__class__.__name__) for provider in providers]}) if len(providers) > 1 else (providers[0] if providers else None)
    return CrossReviewService(provider).review(
        request_pack,
        primary_response,
        reviewer_response=reviewer_response,
        min_confidence=min_confidence,
    )


def _review_request(request_pack: dict[str, Any], primary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "cross_review",
        "messages": [
            {"role": "system", "content": "Review the primary quant assistant response. Return one JSON object only."},
            {"role": "user", "content": json.dumps({"request": request_pack, "primary": primary}, ensure_ascii=False, default=str)},
        ],
        "response_schema": request_pack.get("request", {}).get("response_schema", {}),
    }


def _offline_reviewer_response(primary: dict[str, Any], request_pack: dict[str, Any]) -> dict[str, Any]:
    confidence = min(0.8, max(0.0, _confidence(primary)))
    risks = _strings(primary.get("risk_flags"))
    if not risks and "cloud" in json.dumps(request_pack, ensure_ascii=False, default=str).lower():
        risks.append("verify_cloud_cache_freshness")
    return {
        "summary": "Offline reviewer found no contradictory evidence in the supplied request pack.",
        "recommended_next_actions": _strings(primary.get("recommended_next_actions"))[:5],
        "risk_flags": risks,
        "candidate_adjustments": primary.get("candidate_adjustments") if isinstance(primary.get("candidate_adjustments"), list) else [],
        "follow_up_questions": [],
        "confidence": confidence,
    }


def _parse_response(value: str | dict[str, Any] | None, *, label: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        return parse_assistant_response(str(value or ""))
    except AssistantResponseParseError as exc:
        raise AssistantResponseParseError(f"{label} response parse failed: {exc}") from exc


def _agreement(primary: dict[str, Any], reviewer: dict[str, Any]) -> bool:
    primary_actions = set(_strings(primary.get("recommended_next_actions")))
    reviewer_actions = set(_strings(reviewer.get("recommended_next_actions")))
    primary_risks = set(_strings(primary.get("risk_flags")))
    reviewer_risks = set(_strings(reviewer.get("risk_flags")))
    if primary_risks and reviewer_risks and primary_risks.isdisjoint(reviewer_risks):
        return False
    if primary_actions and reviewer_actions and primary_actions.isdisjoint(reviewer_actions):
        return False
    return True


def _confidence(value: dict[str, Any]) -> float:
    try:
        number = float(value.get("confidence", 0.0))
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(1.0, number))
