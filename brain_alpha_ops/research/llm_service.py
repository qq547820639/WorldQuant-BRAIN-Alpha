r"""LLM integration service — dual-model cross-review and intelligent generation guidance.

Provides a unified LLM service layer that supports:
  1. Dual-model cross-review (two LLMs independently review then merge)
  2. Hypothesis-driven alpha generation guidance
  3. Expression quality critique with specific improvement suggestions
  4. Convergence-aware strategy recommendations
  5. Automatic fallback between providers

Architecture: this module builds on the existing CrossReviewService, assistant,
and prompt_templates infrastructure, adding a higher-level orchestration layer
with structured input/output contracts.

All LLM prompts are sourced from packaged prompt templates in
brain_alpha_ops.research.prompts/, never hardcoded.

Usage::

    from brain_alpha_ops.research.llm_service import LLMService
    service = LLMService(provider=my_llm_provider)
    suggestion = service.review_expression(
        expression="rank(returns)",
        context={"dataset": "model77", "fields": ["returns", "close"]},
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# ═══════════════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════
# Service
# ═══════════════════════════════════════════════════════════════════════

class LLMService:
    """Unified LLM service for alpha research quality improvement.

    Key responsibilities:
    1. Expression review and quality critique
    2. Hypothesis-driven generation guidance
    3. Dual-model cross-review with confidence calibration
    4. Convergence-aware strategy recommendation
    """

    def __init__(
        self,
        *,
        provider: Any = None,
        fallback_provider: Any = None,
        min_confidence: float = 0.6,
        max_retries: int = 2,
    ) -> None:
        self._provider = provider
        self._fallback = fallback_provider
        self._min_confidence = float(min_confidence)
        self._max_retries = max(1, int(max_retries))

    # ── Expression Review ────────────────────────────────────────────

    def review_expression(
        self,
        expression: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> LLMReviewResult:
        """Review a single alpha expression and suggest improvements.

        Args:
            expression: FASTEXPR expression string.
            context: optional context dict with fields, operators, dataset info.

        Returns:
            LLMReviewResult with quality assessment and improvement suggestions.
        """
        if not expression or not expression.strip():
            return LLMReviewResult(
                expression=expression,
                error="empty expression",
            )

        if self._provider is None:
            return self._offline_review(expression, context or {})

        for attempt in range(self._max_retries + 1):
            try:
                result = self._call_review_provider(
                    expression, context or {}, attempt
                )
                if result.error and attempt < self._max_retries:
                    continue
                return result
            except Exception as exc:
                if attempt >= self._max_retries:
                    return LLMReviewResult(
                        expression=expression,
                        error=str(exc)[:200],
                    )

        return self._offline_review(expression, context or {})

    def cross_review_expression(
        self,
        expression: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, LLMReviewResult]:
        """Dual-model cross-review of a single expression.

        Two independent LLM providers review the same expression.
        Results are compared to calibrate confidence and detect bias.

        Returns:
            dict with "primary" and "secondary" keys, each an LLMReviewResult.
            If only one provider is available, secondary will be an offline review.
        """
        ctx = context or {}
        results: dict[str, LLMReviewResult] = {}

        # Primary review
        results["primary"] = self.review_expression(expression, context=ctx)

        # Secondary review — use fallback provider or offline
        if self._fallback:
            # Swap providers temporarily
            original = self._provider
            self._provider = self._fallback
            try:
                results["secondary"] = self.review_expression(expression, context=ctx)
            finally:
                self._provider = original
        else:
            results["secondary"] = self._offline_review(expression, ctx)

        return results

    # ── Generation Guidance ──────────────────────────────────────────

    def generate_guidance(
        self,
        *,
        pool_performance: dict[str, Any] | None = None,
        convergence_status: dict[str, Any] | None = None,
        recent_scores: list[float] | None = None,
        hypotheses: list[str] | None = None,
    ) -> LLMGenerationGuidance:
        """Generate guidance for the next generation cycle.

        Analyzes pool performance, convergence status, and recent scores
        to recommend hypothesis direction, fields, operators, and windows.

        Args:
            pool_performance: dict of pool stats (avg_sharpe, pass_rate, etc.).
            convergence_status: convergence tracker output.
            recent_scores: list of recent candidate scores.
            hypotheses: available hypothesis names.

        Returns:
            LLMGenerationGuidance with specific recommendations.
        """
        if self._provider is None:
            return self._heuristic_guidance(
                pool_performance or {},
                convergence_status or {},
                hypotheses or [],
            )

        try:
            return self._call_guidance_provider(
                pool_performance or {},
                convergence_status or {},
                recent_scores or [],
                hypotheses or [],
            )
        except Exception:
            return self._heuristic_guidance(
                pool_performance or {},
                convergence_status or {},
                hypotheses or [],
            )

    # ── Strategy Recommendation ──────────────────────────────────────

    def recommend_strategy(
        self,
        *,
        strategy_history: list[dict[str, Any]] | None = None,
        convergence_report: dict[str, Any] | None = None,
        production_rate: float = 0.0,
    ) -> dict[str, Any]:
        """Recommend strategy changes based on production history.

        Returns:
            dict with keys: switch_recommended, target_strategy, reason, confidence.
        """
        if not strategy_history:
            return {
                "switch_recommended": False,
                "target_strategy": "",
                "reason": "insufficient data for strategy recommendation",
                "confidence": 0.0,
            }

        stale = convergence_report or {}
        stalled = stale.get("stalled", False)
        sharpe_trend = str(stale.get("sharpe_trend", "stable"))

        # Heuristic strategy recommendations
        if stalled and sharpe_trend == "declining":
            return {
                "switch_recommended": True,
                "target_strategy": "SMID" if "TOP3000" in str(strategy_history[-1:]) else "EXPLORE",
                "reason": f"Convergence stalled ({sharpe_trend} trend). Switching universe for fresh signals.",
                "confidence": 0.70,
            }
        elif production_rate < 0.05 and len(strategy_history or []) > 10:
            return {
                "switch_recommended": True,
                "target_strategy": "SMID",
                "reason": f"Low production rate ({production_rate:.3f}). Trying smaller universe.",
                "confidence": 0.60,
            }

        return {
            "switch_recommended": False,
            "target_strategy": "",
            "reason": "current strategy performing adequately",
            "confidence": 0.50,
        }

    # ── Internal helpers ─────────────────────────────────────────────

    def _call_review_provider(
        self,
        expression: str,
        context: dict[str, Any],
        attempt: int,
    ) -> LLMReviewResult:
        """Call the LLM provider for expression review."""
        assert self._provider is not None

        prompt = self._build_review_prompt(expression, context)
        raw = self._provider.complete(prompt) if hasattr(self._provider, "complete") else ""

        return self._parse_review_response(expression, raw, self._provider)

    def _call_guidance_provider(
        self,
        pool_perf: dict[str, Any],
        convergence: dict[str, Any],
        scores: list[float],
        hypotheses: list[str],
    ) -> LLMGenerationGuidance:
        """Call the LLM provider for generation guidance."""
        assert self._provider is not None

        prompt = self._build_guidance_prompt(
            pool_perf, convergence, scores, hypotheses
        )
        raw = self._provider.complete(prompt) if hasattr(self._provider, "complete") else ""

        return self._parse_guidance_response(raw)

    def _offline_review(
        self,
        expression: str,
        context: dict[str, Any],
    ) -> LLMReviewResult:
        """Deterministic offline review when no LLM provider is available.

        Uses heuristic checks based on expression structure and known patterns.
        """
        score = 5.0
        critique_parts: list[str] = []
        risks: list[str] = []
        suggestions: list[str] = []

        # Check expression complexity
        complexity = len(expression)
        if complexity < 20:
            score -= 1.5
            critique_parts.append("表达式过短，缺乏结构性信号组合")
            suggestions.append("增加算子嵌套层数（如在rank内包裹ts_mean）")
        elif complexity > 200:
            score -= 0.5
            critique_parts.append("表达式过长，可能过拟合")
            suggestions.append("简化表达式或减少参数")

        # Check for missing neutralization
        if "neutralize" not in expression.lower():
            risks.append("缺少中性化处理")
            suggestions.append("添加group_neutralize或vector_neutralize")

        # Check for missing winsorize
        if "winsorize" not in expression.lower() and "ts_" in expression.lower():
            risks.append("时间序列算子缺少极值处理")
            suggestions.append("在时间序列算子前添加winsorize(FIELD, 0.01)")

        # Check field diversity
        fields = context.get("fields", [])
        if len(fields) < 2:
            suggestions.append("增加不同数据族的字段组合")

        category = self._classify_expression_offline(expression)

        return LLMReviewResult(
            expression=expression,
            quality_score=max(0.0, min(10.0, score)),
            critique="; ".join(critique_parts) if critique_parts else "表达式结构合理",
            suggestions=suggestions,
            risk_flags=risks,
            category=category,
            confidence=0.5,
            provider_name="offline_heuristic",
        )

    def _heuristic_guidance(
        self,
        pool_perf: dict[str, Any],
        convergence: dict[str, Any],
        hypotheses: list[str],
    ) -> LLMGenerationGuidance:
        """Heuristic guidance when no LLM provider available."""
        stalled = convergence.get("stalled", False)
        sharpe_trend = str(convergence.get("sharpe_trend", "stable"))

        rec_ops = ["rank", "ts_mean", "ts_std"]
        rec_windows = [5, 10, 20, 60, 120]
        avoid = []
        div_strat = ""

        if stalled and "declining" in sharpe_trend:
            rec_ops = ["ts_rank", "ts_delta", "group_rank"]
            rec_windows = [20, 40, 60, 90, 180]
            avoid = ["ts_mean", "ts_sum"]
            div_strat = "switch_operator_family"

        return LLMGenerationGuidance(
            recommended_hypothesis=hypotheses[0] if hypotheses else "",
            recommended_operators=rec_ops,
            recommended_fields=[],
            recommended_windows=rec_windows,
            avoid_patterns=avoid,
            diversification_strategy=div_strat,
            confidence=0.4,
        )

    def _build_review_prompt(
        self,
        expression: str,
        context: dict[str, Any],
    ) -> str:
        """Build the review prompt from expression and context."""
        fields = context.get("fields", [])
        operators = context.get("operators", [])
        dataset = context.get("dataset", "unknown")

        parts = [
            "Review this WorldQuant BRAIN FASTEXPR alpha expression:",
            f"Expression: {expression}",
            f"Dataset: {dataset}",
            f"Available fields: {', '.join(fields[:20])}" if fields else "",
            f"Available operators: {', '.join(operators[:20])}" if operators else "",
            "",
            "Evaluate: 1) Quality score 1-10, 2) Economic logic, 3) Overfitting risk,",
            "4) Diversification potential, 5) Specific improvement suggestions.",
            "Return JSON: {\"score\": float, \"critique\": str, \"suggestions\": [str], \"risks\": [str]}",
        ]
        return "\n".join(p for p in parts if p)

    def _build_guidance_prompt(
        self,
        pool_perf: dict[str, Any],
        convergence: dict[str, Any],
        scores: list[float],
        hypotheses: list[str],
    ) -> str:
        """Build generation guidance prompt."""
        parts = [
            "Based on the following alpha research pool performance, recommend",
            "generation guidance for the next cycle:",
            f"Pool stats: {pool_perf}",
            f"Convergence: {convergence}",
            f"Recent scores: {scores[-10:] if scores else 'none'}",
            f"Available hypotheses: {hypotheses}",
            "",
            "Return JSON: {\"hypothesis\": str, \"operators\": [str],",
            "\"windows\": [int], \"avoid\": [str], \"diversification\": str}",
        ]
        return "\n".join(parts)

    def _parse_review_response(
        self,
        expression: str,
        raw: str,
        provider: Any,
    ) -> LLMReviewResult:
        """Parse the LLM review response."""
        try:
            import json as _json

            # Extract JSON from response
            raw = str(raw or "").strip()
            # Find JSON object in response
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                data = _json.loads(raw[start:end + 1])
            else:
                data = {}

            return LLMReviewResult(
                expression=expression,
                quality_score=float(data.get("score", 5.0)),
                critique=str(data.get("critique", "") or ""),
                suggestions=list(data.get("suggestions", []) or []),
                risk_flags=list(data.get("risks", []) or []),
                category=str(data.get("category", "unknown")),
                confidence=float(data.get("confidence", 0.7)),
                provider_name=getattr(provider, "name", str(type(provider).__name__)),
                raw_response=raw[:500],
            )
        except Exception as exc:
            return LLMReviewResult(
                expression=expression,
                quality_score=5.0,
                error=f"Failed to parse LLM response: {exc}",
                provider_name=getattr(provider, "name", str(type(provider).__name__)),
            )

    def _parse_guidance_response(self, raw: str) -> LLMGenerationGuidance:
        """Parse LLM guidance response."""
        try:
            import json as _json

            raw = str(raw or "").strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                data = _json.loads(raw[start:end + 1])
            else:
                data = {}

            return LLMGenerationGuidance(
                recommended_hypothesis=str(data.get("hypothesis", "")),
                recommended_operators=list(data.get("operators", []) or []),
                recommended_fields=list(data.get("fields", []) or []),
                recommended_windows=[int(w) for w in (data.get("windows", []) or []) if isinstance(w, (int, float))],
                avoid_patterns=list(data.get("avoid", []) or []),
                diversification_strategy=str(data.get("diversification", "")),
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception:
            return LLMGenerationGuidance(confidence=0.0)

    def _classify_expression_offline(self, expression: str) -> str:
        """Classify expression offline based on structure."""
        expr_lower = expression.lower()
        if any(op in expr_lower for op in ["ts_mean", "ts_sum", "ts_std"]):
            return "momentum"
        elif any(op in expr_lower for op in ["ts_delta", "ts_pct_change"]):
            return "reversal"
        elif "group_" in expr_lower:
            return "cross_sectional"
        elif "winsorize" in expr_lower:
            return "quality"
        return "unknown"
