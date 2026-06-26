"""Cross-Review Pipeline orchestrator.

Re-exported via ``brain_alpha_ops.research.cross_review_pipeline``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_data, redact_error_message

from brain_alpha_ops.research.cross_review_pipeline._evidence import (
    KnowledgeEvidenceChecker,
)
from brain_alpha_ops.research.cross_review_pipeline._decision import (
    ReviewDecisionEngine,
)
from brain_alpha_ops.research.cross_review_pipeline._types import (
    REVIEW_PIPELINE_SCHEMA,
    EvidenceCheckResult,
    ReviewDecision,
    ReviewableCandidate,
    _dedup,
    _ensure_dict_response,
    _extract_claims,
)

logger = logging.getLogger("brain_alpha_ops.research.cross_review_pipeline")


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
            from brain_alpha_ops.research.llm_review import (
                cross_review_assistant_response,
            )

            review_result = cross_review_assistant_response(
                request_pack=request_pack,
                primary_response=primary_response,
                reviewer_response=reviewer_response,
                min_confidence=min_confidence,
            )
        except Exception as exc:
            logger.warning(
                "cross_review failed, falling back to offline reviewer: %s",
                redact_error_message(exc, max_length=160),
            )
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
            evidence_checks=[asdict(er) for er in evidence_results],
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
                "decision": asdict(decision),
                "review_result": review_result,
            })
            audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("failed to write review audit trail: %s", redact_error_message(exc, max_length=160))
