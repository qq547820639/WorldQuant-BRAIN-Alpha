"""Data models for LLM review results and generation guidance."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMReviewResult:
    """Result of an LLM expression review."""

    expression: str
    quality_score: float = 0.0
    critique: str = ""
    suggestions: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    category: str = "unknown"
    confidence: float = 0.0
    provider_name: str = "none"
    raw_response: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "quality_score": round(self.quality_score, 2),
            "critique": self.critique,
            "suggestions": self.suggestions,
            "risk_flags": self.risk_flags,
            "category": self.category,
            "confidence": round(self.confidence, 4),
            "provider_name": self.provider_name,
            "error": self.error,
        }


@dataclass
class LLMGenerationGuidance:
    """Guidance for the next generation cycle from LLM analysis."""

    recommended_hypothesis: str = ""
    recommended_operators: list[str] = field(default_factory=list)
    recommended_fields: list[str] = field(default_factory=list)
    recommended_windows: list[int] = field(default_factory=list)
    avoid_patterns: list[str] = field(default_factory=list)
    diversification_strategy: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_hypothesis": self.recommended_hypothesis,
            "recommended_operators": self.recommended_operators,
            "recommended_fields": self.recommended_fields,
            "recommended_windows": self.recommended_windows,
            "avoid_patterns": self.avoid_patterns,
            "diversification_strategy": self.diversification_strategy,
            "confidence": round(self.confidence, 4),
        }
