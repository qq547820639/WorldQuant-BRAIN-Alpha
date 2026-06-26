"""Provider-neutral LLM cross-review helpers.

Re-export from the ``llm_review`` subpackage for backward compatibility.

The original monolithic ``llm_review.py`` was split into the
``brain_alpha_ops.research.llm_review`` subpackage. This module re-exports
the full public API surface (plus private helpers referenced by tests and
internal callers) so legacy imports continue to work.

Sub-modules:
  - ``_utils``        : ``_strings``, ``_digest_json``, ``_digest_text``
  - ``_providers``    : ``LLMProvider``, ``StaticLLMProvider``,
                        ``FallbackLLMProvider``, ``LLMProviderRouter``,
                        ``OpenAICompatibleProvider``, ``_providers_from_env``,
                        ``_optional_float``
  - ``_cross_review`` : ``CrossReviewService``,
                        ``cross_review_assistant_response``,
                        ``_review_request``, ``_offline_reviewer_response``,
                        ``_parse_response``, ``_agreement``, ``_confidence``
  - ``_ledger``       : ``PromptRunLedger``
"""

from __future__ import annotations

from brain_alpha_ops.research.llm_review._utils import (  # noqa: F401
    _digest_json,
    _digest_text,
    _strings,
)
from brain_alpha_ops.research.llm_review._providers import (  # noqa: F401
    FallbackLLMProvider,
    LLMProvider,
    LLMProviderRouter,
    OpenAICompatibleProvider,
    StaticLLMProvider,
    _optional_float,
    _providers_from_env,
)
from brain_alpha_ops.research.llm_review._cross_review import (  # noqa: F401
    CROSS_REVIEW_SCHEMA_VERSION,
    CrossReviewService,
    cross_review_assistant_response,
    _agreement,
    _confidence,
    _offline_reviewer_response,
    _parse_response,
    _review_request,
)
from brain_alpha_ops.research.llm_review._ledger import (  # noqa: F401
    PROMPT_RUN_LEDGER_SCHEMA_VERSION,
    PromptRunLedger,
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
