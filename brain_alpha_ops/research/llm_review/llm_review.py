"""Provider-neutral LLM cross-review helpers, utilities, and prompt ledger.

Merged from the former ``_utils``, ``_cross_review``, and ``_ledger``
sub-modules.  Provider abstractions live in ``llm_review_providers``.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    parse_assistant_response,
)

from brain_alpha_ops.research.llm_review.llm_review_providers import (
    LLMProvider,
    LLMProviderRouter,
    _providers_from_env,
)


# ── Shared digest and string helpers ──────────────────────────────────────

def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _digest_json(value: Any) -> str:
    return _digest_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _digest_text(value: str) -> str:
    return sha256(str(value or "").encode("utf-8", errors="ignore")).hexdigest()[:16]


# ── Cross-review service and orchestration ────────────────────────────────

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


# ── Append-only prompt run ledger ─────────────────────────────────────────

PROMPT_RUN_LEDGER_SCHEMA_VERSION = "prompt_run_ledger.v1"


class PromptRunLedger:
    """Append-only prompt run ledger that never stores provider secrets."""

    def __init__(self, storage_dir: str | Path):
        self.path = Path(storage_dir) / "prompt_runs.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        request_pack: dict[str, Any],
        model: str = "",
        temperature: float | None = None,
        response_text: str = "",
        parse_status: str = "",
    ) -> dict[str, Any]:
        row = redact_data(
            {
                "schema_version": PROMPT_RUN_LEDGER_SCHEMA_VERSION,
                "timestamp": utc_now(),
                "prompt_digest": request_pack.get("prompt_digest") or _digest_text(str(request_pack.get("prompt") or "")),
                "context_digest": request_pack.get("context_digest") or _digest_json(request_pack.get("context_pack") or {}),
                "model": model,
                "temperature": temperature,
                "response_digest": _digest_text(response_text),
                "parse_status": parse_status or "unknown",
            }
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        return row
