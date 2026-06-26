"""Re-export from the ``llm_service`` subpackage for backward compatibility.

The original monolithic ``llm_service.py`` was split into the
``brain_alpha_ops.research.llm_service`` subpackage. This module re-exports
the full public API surface so legacy imports continue to work.

Sub-modules:
  - ``_types``             : ``LLMReviewResult``, ``LLMGenerationGuidance`` dataclasses
  - ``_ledger``            : ``LLMCallLedger`` + token-budget constants
  - ``_service_review``    : ``_ServiceReviewMixin`` (expression review methods)
  - ``_service_guidance``  : ``_ServiceGuidanceMixin`` (guidance + strategy methods)
  - ``_service``           : ``LLMService`` class assembly
"""
from __future__ import annotations

from brain_alpha_ops.research.llm_service._types import *  # noqa: F401,F403
from brain_alpha_ops.research.llm_service._ledger import *  # noqa: F401,F403
from brain_alpha_ops.research.llm_service._service import *  # noqa: F401,F403

# Explicit re-exports for clarity and to ensure all public symbols are
# available via ``from brain_alpha_ops.research.llm_service import X``.
from brain_alpha_ops.research.llm_service._types import (  # noqa: F401
    LLMGenerationGuidance,
    LLMReviewResult,
)
from brain_alpha_ops.research.llm_service._ledger import (  # noqa: F401
    LLM_CALL_MIN_INTERVAL_SECONDS,
    LLM_CALL_TOKEN_BUDGET_PER_RUN,
    LLMCallLedger,
)
from brain_alpha_ops.research.llm_service._service import (  # noqa: F401
    LLMService,
)
