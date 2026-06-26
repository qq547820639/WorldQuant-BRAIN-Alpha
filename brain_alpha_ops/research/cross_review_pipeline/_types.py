"""Types and constants for the cross-review pipeline subpackage.

Re-exported via ``brain_alpha_ops.research.cross_review_pipeline``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger("brain_alpha_ops.research.cross_review_pipeline")

REVIEW_PIPELINE_SCHEMA = "dual_llm_review_pipeline.v2"

# ═══════════════════════════════════════════════════════════════════════════
# Protocols & Adapters
# ═══════════════════════════════════════════════════════════════════════════

class ReviewableCandidate(Protocol):
    """Minimal protocol for a candidate that can be reviewed."""

    @property
    def alpha_id(self) -> str: ...
    @property
    def expression(self) -> str: ...
    @property
    def family(self) -> str: ...
    @property
    def hypothesis(self) -> str: ...


# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class EvidenceCheckResult:
    """Result of checking a primary LLM claim against the knowledge base."""

    claim_key: str = ""
    claim_text: str = ""
    matched_rule: str = ""           # matching rule entry_id
    matched_rule_title: str = ""
    matched_failure: str = ""         # matching failure entry_id
    matched_failure_title: str = ""
    evidence_score: float = 0.0       # 0.0–1.0: how well evidence supports claim
    risk_level: str = "low"           # low | medium | high


@dataclass
class ReviewDecision:
    """Structured output from the review decision engine."""

    decision: str = "conservative_review_required"
    # One of: accept | accept_with_warnings | conservative_review_required | reject

    confidence_score: float = 0.0
    # Aggregate confidence (0.0–1.0) from primary, reviewer, and evidence.

    primary_confidence: float = 0.0
    reviewer_confidence: float = 0.0
    evidence_support: float = 0.0

    agreement: bool = False
    conservative: bool = True

    risk_flags: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    evidence_checks: list[dict[str, Any]] = field(default_factory=list)

    primary_digest: str = ""
    reviewer_digest: str = ""

    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_dict_response(response: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, dict):
        return dict(response)
    try:
        return json.loads(str(response))
    except json.JSONDecodeError:
        return {"summary": str(response)[:500], "confidence": 0.3, "risk_flags": ["unparseable_response"]}


def _extract_claims(primary: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract structured claims from a parsed primary response."""
    claims = []
    # Field recommendations
    fields = primary.get("preferred_fields") or primary.get("recommended_fields") or []
    if isinstance(fields, list):
        for field in fields:
            claims.append({"type": "field_recommendation", "text": str(field), "confidence": primary.get("confidence", 0.5)})
    # Operator recommendations
    ops = primary.get("preferred_operators") or primary.get("recommended_operators") or []
    if isinstance(ops, list):
        for op in ops:
            claims.append({"type": "operator_recommendation", "text": str(op), "confidence": primary.get("confidence", 0.5)})
    # Family recommendations
    families = primary.get("recommended_families") or []
    if isinstance(families, list):
        for fam in families:
            claims.append({"type": "family_recommendation", "text": str(fam), "confidence": primary.get("confidence", 0.5)})
    # Actions
    actions = primary.get("recommended_next_actions") or []
    if isinstance(actions, list):
        for action in actions:
            claims.append({"type": "action_recommendation", "text": str(action), "confidence": primary.get("confidence", 0.5)})
    return claims


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result


# Lazy import to avoid pulling json at module import time in case of partial
# initialization.  The original module imported ``json`` at the top level so
# we keep the same behavior here.
import json  # noqa: E402
