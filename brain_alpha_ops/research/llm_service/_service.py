"""``LLMService`` — unified LLM service for alpha research quality improvement.

Assembles the review and guidance mixins into the final ``LLMService`` class.

Key responsibilities:
1. Expression review and quality critique
2. Hypothesis-driven generation guidance
3. Dual-model cross-review with confidence calibration
4. Convergence-aware strategy recommendation
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research.llm_service._ledger import LLMCallLedger
from brain_alpha_ops.research.llm_service._service_review import _ServiceReviewMixin
from brain_alpha_ops.research.llm_service._service_guidance import _ServiceGuidanceMixin


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
