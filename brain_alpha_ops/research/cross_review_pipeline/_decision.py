"""Review Decision Engine for the cross-review pipeline.

Re-exported via ``brain_alpha_ops.research.cross_review_pipeline``.
"""
from __future__ import annotations

import math
from typing import Any

from brain_alpha_ops.research.cross_review_pipeline._types import (
    ReviewDecision,
)


class ReviewDecisionEngine:
    """Aggregate primary, reviewer, and evidence checks into a single decision.

    Decision logic:
      1. If primary_confidence < 0.3 → reject (too uncertain)
      2. If reviewer disagrees AND reviewer_confidence >= 0.5 → conservative review
      3. If evidence support < 0.3 → reject or conservative review
      4. If all agree AND evidence >= 0.6 → accept
      5. If agree but evidence 0.4–0.6 → accept_with_warnings
    """

    MIN_PRIMARY_CONFIDENCE: float = 0.3
    MIN_EVIDENCE_ACCEPT: float = 0.6
    MIN_EVIDENCE_WARN: float = 0.4
    MIN_REVIEWER_WEIGHT: float = 0.5

    def decide(
        self,
        *,
        primary_confidence: float,
        reviewer_confidence: float,
        agreement: bool,
        evidence_support: float,
        risk_flags: list[str] | None = None,
        recommendations: list[str] | None = None,
        evidence_checks: list[dict[str, Any]] | None = None,
    ) -> ReviewDecision:
        # Sanitize NaN inputs
        if math.isnan(primary_confidence):
            primary_confidence = 0.0
        if math.isnan(reviewer_confidence):
            reviewer_confidence = 0.0
        if math.isnan(evidence_support):
            evidence_support = 0.0

        risk_flags = risk_flags or []
        recommendations = recommendations or []
        evidence_checks = evidence_checks or []

        decision = ReviewDecision(
            primary_confidence=primary_confidence,
            reviewer_confidence=reviewer_confidence,
            evidence_support=evidence_support,
            agreement=agreement,
            risk_flags=list(risk_flags),
            recommendations=list(recommendations),
            evidence_checks=[dict(ec) for ec in evidence_checks],
        )

        # ── Step 1: primary too uncertain → reject ──
        if primary_confidence < self.MIN_PRIMARY_CONFIDENCE:
            decision.decision = "reject"
            decision.conservative = True
            decision.confidence_score = primary_confidence
            decision.recommendations.append("Primary LLM confidence too low; regenerate with better context or different prompt.")
            return decision

        # ── Step 2: reviewer disagrees with high confidence → conservative ──
        if not agreement and reviewer_confidence >= self.MIN_REVIEWER_WEIGHT:
            decision.decision = "conservative_review_required"
            decision.conservative = True
            decision.confidence_score = (primary_confidence + reviewer_confidence + evidence_support) / 3
            decision.recommendations.append("LLMs disagree; review both perspectives and adopt the more conservative one.")
            return decision

        # ── Step 3: evidence too weak → reject/ conservative ──
        if evidence_support < self.MIN_EVIDENCE_WARN:
            decision.decision = "reject" if evidence_support < 0.2 else "conservative_review_required"
            decision.conservative = True
            decision.confidence_score = max(primary_confidence, evidence_support)
            decision.recommendations.append("Knowledge base evidence does not support primary LLM claims; verify before proceeding.")
            return decision

        # ── Step 4: strong consensus → accept ──
        if agreement and evidence_support >= self.MIN_EVIDENCE_ACCEPT:
            decision.decision = "accept"
            decision.conservative = False
            decision.confidence_score = (primary_confidence + reviewer_confidence + evidence_support) / 3
            return decision

        # ── Step 5: moderate → accept with warnings ──
        decision.decision = "accept_with_warnings"
        decision.conservative = False
        decision.confidence_score = (primary_confidence + reviewer_confidence + evidence_support) / 3
        decision.recommendations.append("Accepted with warnings; monitor closely in subsequent cycles.")
        return decision
