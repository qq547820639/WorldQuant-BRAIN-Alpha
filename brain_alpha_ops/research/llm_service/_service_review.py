"""Expression-review mixin for ``LLMService``."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research.llm_service._types import LLMReviewResult


class _ServiceReviewMixin:
    """Expression review and cross-review methods for ``LLMService``."""

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

    def _call_review_provider(
        self,
        expression: str,
        context: dict[str, Any],
        attempt: int,
    ) -> LLMReviewResult:
        """Call the LLM provider for expression review."""
        if self._provider is None:
            raise RuntimeError("LLM provider is not initialized; call configure() before use")

        prompt = self._build_review_prompt(expression, context)
        raw = self._provider.complete(prompt) if hasattr(self._provider, "complete") else ""

        return self._parse_review_response(expression, raw, self._provider)

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
