"""Re-export from the ``llm_service`` subpackage for backward compatibility.

The original monolithic ``llm_service.py`` was split into the
``brain_alpha_ops.research.llm_service`` subpackage and has since been
re-consolidated into two physical modules:
  - ``llm_service``        : ``LLMGenerationGuidance``, ``LLMCallLedger``,
                             ``_ServiceGuidanceMixin``, ``LLMService``
  - ``llm_service_review`` : ``LLMReviewResult``, ``_ServiceReviewMixin``
"""
from __future__ import annotations

from brain_alpha_ops.research.llm_service.llm_service import *  # noqa: F401,F403
from brain_alpha_ops.research.llm_service.llm_service_review import *  # noqa: F401,F403

# Explicit re-exports for clarity and to ensure all public symbols are
# available via ``from brain_alpha_ops.research.llm_service import X``.
from brain_alpha_ops.research.llm_service.llm_service import (  # noqa: F401
    LLM_CALL_MIN_INTERVAL_SECONDS,
    LLM_CALL_TOKEN_BUDGET_PER_RUN,
    LLMCallLedger,
    LLMGenerationGuidance,
    LLMService,
)
from brain_alpha_ops.research.llm_service.llm_service_review import (  # noqa: F401
    LLMReviewResult,
)

__all__ = [
    # Public API from _types
    "LLMGenerationGuidance",
    "LLMReviewResult",
    # Public API from _ledger
    "LLM_CALL_MIN_INTERVAL_SECONDS",
    "LLM_CALL_TOKEN_BUDGET_PER_RUN",
    "LLMCallLedger",
    # Public API from _service
    "LLMService",
]
