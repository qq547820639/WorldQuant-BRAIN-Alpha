"""Enhanced dual-LLM cross-review with knowledge base integration.

Extends the existing CrossReviewService with:
  1. Automatic triggering based on confidence thresholds and risk heuristics.
  2. Knowledge base evidence comparison (fact-checking against structured rules).
  3. Structured disagreement resolution with conservative fallback.
  4. Pipeline-ready integration hook for seamless alpha submission gating.

Architecture
------------
    CrossReviewPipeline
     ├── CrossReviewService (existing — llm_review.py)
     │   ├── Primary LLM response parsing
     │   ├── Reviewer LLM (or offline fallback)
     │   └── Agreement detection
     ├── KnowledgeEvidenceChecker (NEW)
     │   ├── Match primary claims against rules layer
     │   ├── Check for forbidden patterns in failures layer
     │   └── Score evidence alignment
     ├── ReviewDecisionEngine (NEW)
     │   ├── Confidence-weighted consensus
     │   ├── Disagreement resolution (conservative by default)
     │   └── Structured recommendations
     └── PipelineIntegrationHook (NEW)
         ├── Pre-generation review
         ├── Pre-submission review
         └── Audit trail recording
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from brain_alpha_ops.redaction import redact_data

logger = logging.getLogger(__name__)

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
# Knowledge Evidence Checker
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


class KnowledgeEvidenceChecker:
    """Checks primary LLM claims against the structured knowledge base.

    For each claim in the primary response:
      - Look for supporting rules in the rules layer.
      - Look for contradictory failures in the failures layer.
      - Score the evidence alignment.
    """

    def __init__(self, storage_dir: str | Path = "data"):
        self.storage_dir = Path(storage_dir)

    def check(
        self,
        primary_claims: list[dict[str, Any]],
        *,
        min_confidence: float = 0.6,
    ) -> list[EvidenceCheckResult]:
        """Check a list of claims against the knowledge base.

        Args:
            primary_claims: List of dicts with 'type', 'text', 'confidence' keys.
            min_confidence: Minimum confidence to consider a claim as potentially valid.

        Returns:
            List of EvidenceCheckResult, one per claim.
        """
        from brain_alpha_ops.research.knowledge_base import StructuredKnowledgeBase

        kb = StructuredKnowledgeBase(self.storage_dir)
        rules = {entry.title.lower(): entry for entry in kb.list_layer("rules")}
        failures = {entry.title.lower(): entry for entry in kb.list_layer("failures")}

        results: list[EvidenceCheckResult] = []
        for claim in primary_claims:
            result = EvidenceCheckResult(
                claim_key=str(claim.get("type", "") or ""),
                claim_text=str(claim.get("text", "") or ""),
            )
            claim_text_lower = result.claim_text.lower()

            # Check against rules (supportive evidence)
            for rule_title, rule_entry in rules.items():
                if any(word in claim_text_lower for word in rule_title.split()):
                    if not result.matched_rule or rule_entry.confidence > result.evidence_score:
                        result.matched_rule = rule_entry.entry_id
                        result.matched_rule_title = rule_entry.title
                        result.evidence_score = max(result.evidence_score, rule_entry.confidence)

            # Check against failures (contradictory evidence)
            for fail_title, fail_entry in failures.items():
                if any(word in claim_text_lower for word in fail_title.split()):
                    result.matched_failure = fail_entry.entry_id
                    result.matched_failure_title = fail_entry.title
                    result.evidence_score = max(0.0, result.evidence_score - fail_entry.confidence * 0.5)

            # Determine risk level
            if result.evidence_score < 0.3:
                result.risk_level = "high"
            elif result.evidence_score < 0.6:
                result.risk_level = "medium"
            else:
                result.risk_level = "low"

            results.append(result)

        return results


# ═══════════════════════════════════════════════════════════════════════════
# Review Decision Engine
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# Cross-Review Pipeline (orchestrator)
# ═══════════════════════════════════════════════════════════════════════════

class CrossReviewPipeline:
    """Orchestrates the full dual-LLM cross-review workflow.

    Usage::

        pipeline = CrossReviewPipeline(storage_dir="data")
        decision = pipeline.review(
            request_pack=context,
            primary_response=assistant_output,
            candidate=candidate,
        )
        if decision.decision == "accept":
            proceed_with_submission()
    """

    def __init__(
        self,
        storage_dir: str | Path = "data",
        *,
        auto_trigger_min_confidence: float = 0.6,
        auto_trigger_risk_threshold: str = "medium",
    ):
        self.storage_dir = Path(storage_dir)
        self.auto_trigger_min_confidence = auto_trigger_min_confidence
        self.auto_trigger_risk_threshold = auto_trigger_risk_threshold
        self.engine = ReviewDecisionEngine()
        self.evidence_checker = KnowledgeEvidenceChecker(storage_dir)

    def review(
        self,
        request_pack: dict[str, Any],
        primary_response: str | dict[str, Any],
        *,
        candidate: ReviewableCandidate | None = None,
        reviewer_response: str | dict[str, Any] | None = None,
        min_confidence: float = 0.6,
        force_review: bool = False,
    ) -> ReviewDecision:
        """Run the full cross-review pipeline.

        Args:
            request_pack: The original assistant request context.
            primary_response: Primary LLM output (raw text or parsed dict).
            candidate: Optional candidate for knowledge base evidence checking.
            reviewer_response: Optional pre-generated reviewer response.
            min_confidence: Minimum confidence threshold.
            force_review: If True, runs even if auto-trigger would skip.

        Returns:
            ReviewDecision with structured decision, confidence, and recommendations.
        """
        # ── Auto-trigger heuristic ──
        if not force_review:
            should_review = self._should_trigger_review(primary_response, candidate)
            if not should_review:
                return ReviewDecision(
                    decision="accept",
                    confidence_score=0.8,
                    primary_confidence=0.8,
                    reviewer_confidence=0.8,
                    agreement=True,
                    conservative=False,
                    recommendations=["Auto-skip: confidence high, risk low."],
                )

        # ── Run cross-review ──
        try:
            from brain_alpha_ops.research.llm_review import cross_review_assistant_response

            review_result = cross_review_assistant_response(
                request_pack=request_pack,
                primary_response=primary_response,
                reviewer_response=reviewer_response,
                min_confidence=min_confidence,
            )
        except Exception as exc:
            logger.warning("cross_review failed, falling back to offline reviewer: %s", exc)
            from brain_alpha_ops.research.llm_review import CrossReviewService
            primary = _ensure_dict_response(primary_response)
            service = CrossReviewService(provider=None)
            review_result = service.review(
                request_pack=request_pack,
                primary_response=primary,
                reviewer_response=None,
                min_confidence=min_confidence,
            )

        # ── Extract claims for evidence checking ──
        primary = review_result.get("primary") if isinstance(review_result.get("primary"), dict) else {}
        claims = _extract_claims(primary)

        # ── Run evidence checks ──
        evidence_results = self.evidence_checker.check(claims, min_confidence=min_confidence)
        evidence_support = self._aggregate_evidence(evidence_results)

        # ── Build the decision ──
        risk_flags = list(review_result.get("risk_flags") or [])
        for er in evidence_results:
            if er.risk_level == "high" and er.claim_text:
                risk_flags.append(f"evidence_high_risk: {er.claim_text[:80]}")

        decision = self.engine.decide(
            primary_confidence=review_result.get("primary_confidence", 0.0),
            reviewer_confidence=review_result.get("reviewer_confidence", 0.0),
            agreement=bool(review_result.get("agreement")),
            evidence_support=evidence_support,
            risk_flags=_dedup(risk_flags),
            recommendations=_dedup(primary.get("recommended_next_actions") or []),
            evidence_checks=[er.__dict__ for er in evidence_results],
        )
        decision.primary_digest = str(review_result.get("primary_digest") or "")
        decision.reviewer_digest = str(review_result.get("reviewer_digest") or "")

        # ── Audit trail ──
        self._write_audit(decision, review_result)

        return decision

    def auto_trigger(
        self,
        request_pack: dict[str, Any],
        primary_response: str | dict[str, Any],
        *,
        candidate: ReviewableCandidate | None = None,
    ) -> ReviewDecision:
        """Convenience: run review with defaults and auto-trigger logic."""
        return self.review(
            request_pack=request_pack,
            primary_response=primary_response,
            candidate=candidate,
            min_confidence=self.auto_trigger_min_confidence,
            force_review=False,
        )

    def pre_submission_gate(
        self,
        request_pack: dict[str, Any],
        primary_response: str | dict[str, Any],
        *,
        candidate: ReviewableCandidate,
    ) -> tuple[bool, ReviewDecision]:
        """Pre-submission gate: force review and only allow accept decisions.

        Returns (allowed, decision).
        """
        decision = self.review(
            request_pack=request_pack,
            primary_response=primary_response,
            candidate=candidate,
            min_confidence=self.auto_trigger_min_confidence,
            force_review=True,
        )
        allowed = decision.decision in ("accept", "accept_with_warnings")
        return allowed, decision

    # ── Internals ─────────────────────────────────────────────────────────

    def _should_trigger_review(
        self,
        primary_response: str | dict[str, Any],
        candidate: ReviewableCandidate | None,
    ) -> bool:
        """Heuristic: trigger cross-review when confidence is low or risk is high."""
        primary = _ensure_dict_response(primary_response)
        confidence = float(primary.get("confidence", 0.8))
        if confidence < self.auto_trigger_min_confidence:
            return True
        risk_flags = primary.get("risk_flags")
        if isinstance(risk_flags, list) and risk_flags:
            return True
        if candidate is not None:
            # Check expression complexity as a heuristic
            expression = getattr(candidate, "expression", "")
            if len(expression) > 80:  # Complex expression → review
                return True
        return False

    @staticmethod
    def _aggregate_evidence(results: list[EvidenceCheckResult]) -> float:
        if not results:
            return 0.5
        total = sum(r.evidence_score for r in results)
        penalty = sum(0.3 for r in results if r.matched_failure)
        raw = total / len(results) - penalty / max(1, len(results))
        return max(0.0, min(1.0, raw))

    def _write_audit(self, decision: ReviewDecision, review_result: dict[str, Any]) -> None:
        audit_dir = self.storage_dir / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / f"review_{decision.generated_at[:10]}_{sha256(str(decision).encode()).hexdigest()[:8]}.json"
        try:
            payload = redact_data({
                "schema_version": REVIEW_PIPELINE_SCHEMA,
                "decision": decision.__dict__,
                "review_result": review_result,
            })
            audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("failed to write review audit trail: %s", exc)


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
