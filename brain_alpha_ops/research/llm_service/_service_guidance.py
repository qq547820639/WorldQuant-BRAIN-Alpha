"""Generation-guidance and strategy-recommendation mixin for ``LLMService``."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research.llm_service._types import LLMGenerationGuidance


class _ServiceGuidanceMixin:
    """Generation guidance and strategy recommendation methods for ``LLMService``."""

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

    def _call_guidance_provider(
        self,
        pool_perf: dict[str, Any],
        convergence: dict[str, Any],
        scores: list[float],
        hypotheses: list[str],
    ) -> LLMGenerationGuidance:
        """Call the LLM provider for generation guidance."""
        if self._provider is None:
            raise RuntimeError("LLM provider is not initialized; call configure() before use")

        prompt = self._build_guidance_prompt(
            pool_perf, convergence, scores, hypotheses
        )
        raw = self._provider.complete(prompt) if hasattr(self._provider, "complete") else ""

        return self._parse_guidance_response(raw)

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
