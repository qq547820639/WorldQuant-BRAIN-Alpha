"""Provider-neutral LLM cross-review helpers.

Re-export from the ``llm_review`` subpackage for backward compatibility.

The original monolithic ``llm_review.py`` was split into the
``brain_alpha_ops.research.llm_review`` subpackage and has since been
re-consolidated into two physical modules:
  - ``llm_review``           : utilities, cross-review service, prompt ledger
  - ``llm_review_providers`` : ``LLMProvider``, ``StaticLLMProvider``,
                               ``FallbackLLMProvider``, ``LLMProviderRouter``,
                               ``OpenAICompatibleProvider``, ``_providers_from_env``,
                               ``_optional_float``
"""

from __future__ import annotations

from brain_alpha_ops.research.llm_review.llm_review import (  # noqa: F401
    CROSS_REVIEW_SCHEMA_VERSION,
    PROMPT_RUN_LEDGER_SCHEMA_VERSION,
    CrossReviewService,
    PromptRunLedger,
    cross_review_assistant_response,
    _agreement,
    _confidence,
    _digest_json,
    _digest_text,
    _offline_reviewer_response,
    _parse_response,
    _review_request,
    _strings,
)
from brain_alpha_ops.research.llm_review.llm_review_providers import (  # noqa: F401
    FallbackLLMProvider,
    LLMProvider,
    LLMProviderRouter,
    OpenAICompatibleProvider,
    StaticLLMProvider,
    _optional_float,
    _providers_from_env,
)

__all__ = [
    # Constants
    "CROSS_REVIEW_SCHEMA_VERSION",
    "PROMPT_RUN_LEDGER_SCHEMA_VERSION",
    # Providers
    "LLMProvider",
    "StaticLLMProvider",
    "FallbackLLMProvider",
    "LLMProviderRouter",
    "OpenAICompatibleProvider",
    # Cross-review
    "CrossReviewService",
    "cross_review_assistant_response",
    # Ledger
    "PromptRunLedger",
    # Private helpers (re-exported for monkeypatch/backward-compat)
    "_providers_from_env",
    "_optional_float",
    "_review_request",
    "_offline_reviewer_response",
    "_parse_response",
    "_agreement",
    "_confidence",
    "_strings",
    "_digest_json",
    "_digest_text",
]
