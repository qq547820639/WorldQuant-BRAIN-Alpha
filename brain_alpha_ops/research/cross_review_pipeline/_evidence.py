"""Knowledge Evidence Checker for the cross-review pipeline.

Re-exported via ``brain_alpha_ops.research.cross_review_pipeline``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_alpha_ops.research.cross_review_pipeline._types import (
    EvidenceCheckResult,
)


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
