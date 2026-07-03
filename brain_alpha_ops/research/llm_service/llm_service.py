"""``LLMService`` — unified LLM service for alpha research quality improvement.

Merged from the former ``_types`` (``LLMGenerationGuidance`` only), ``_ledger``,
``_service_guidance``, and ``_service`` sub-modules.  ``LLMReviewResult`` and
``_ServiceReviewMixin`` live in ``llm_service_review`` to avoid a circular
import.

Key responsibilities:
1. Expression review and quality critique
2. Hypothesis-driven generation guidance
3. Dual-model cross-review with confidence calibration
4. Convergence-aware strategy recommendation
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.research.llm_service.llm_service_review import _ServiceReviewMixin


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


# ── Per-process LLM call quota tracker (P3-4) ─────────────────────────────

# P3-4: per-instance token quota.  A pipeline run that loops over hundreds
# of LLM reviews can otherwise burn through the OpenAI quota in a single
# cycle.  The cap is conservative; bump via env if your account is
# provisioned for higher throughput.
LLM_CALL_TOKEN_BUDGET_PER_RUN: int = 200_000
LLM_CALL_MIN_INTERVAL_SECONDS: float = 0.5  # basic rate-limit between calls


class LLMCallLedger:
    """Thread-safe per-process quota tracker for LLM calls (P3-4).

    Tracks cumulative prompt/completion tokens and enforces a soft cap.
    Failures are also counted; ``consecutive_failures`` triggers an
    exponential cool-down (see ``record_failure``).
    """

    def __init__(
        self,
        *,
        token_budget: int = LLM_CALL_TOKEN_BUDGET_PER_RUN,
        min_interval_seconds: float = LLM_CALL_MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token_budget = max(0, int(token_budget))
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._clock = clock
        self._tokens_used: int = 0
        self._calls: int = 0
        self._failures: int = 0
        self._consecutive_failures: int = 0
        self._last_call_at: float = 0.0
        self._lock = threading.Lock()

    def budget_exhausted(self) -> bool:
        with self._lock:
            return self._tokens_used >= self._token_budget

    def record(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int | None = None,
    ) -> None:
        tokens = int(total_tokens) if total_tokens is not None else int(prompt_tokens) + int(completion_tokens)
        with self._lock:
            self._tokens_used += max(0, tokens)
            self._calls += 1
            self._consecutive_failures = 0
            self._last_call_at = self._clock()

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._consecutive_failures += 1

    def wait_for_quota(self) -> None:
        """Sleep until the next call is allowed. Returns immediately if not.

        Implements basic per-call spacing (``min_interval_seconds``) and
        exponential back-off after consecutive failures.
        """
        with self._lock:
            now = self._clock()
            spacing = self._min_interval
            if self._consecutive_failures > 0:
                spacing *= 2 ** min(self._consecutive_failures, 5)
            wait = max(0.0, spacing - (now - self._last_call_at))
        if wait > 0:
            time.sleep(wait)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tokens_used": self._tokens_used,
                "token_budget": self._token_budget,
                "calls": self._calls,
                "failures": self._failures,
                "consecutive_failures": self._consecutive_failures,
            }


# ── Generation-guidance and strategy-recommendation mixin ─────────────────


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


# ── Final ``LLMService`` class assembly ───────────────────────────────────


class LLMService(_ServiceReviewMixin, _ServiceGuidanceMixin):
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
        call_ledger: LLMCallLedger | None = None,
    ) -> None:
        self._provider = provider
        self._fallback = fallback_provider
        self._min_confidence = float(min_confidence)
        self._max_retries = max(1, int(max_retries))
        # P3-4: optional per-process quota tracker.  When None, the service
        # is unbounded; tests and short-lived jobs can opt out.
        self._call_ledger = call_ledger or LLMCallLedger()
