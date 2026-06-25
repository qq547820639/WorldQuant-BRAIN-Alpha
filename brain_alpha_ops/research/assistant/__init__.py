"""Assistant request and response helpers.

This package splits the original ``assistant.py`` into focused sub-modules
while preserving the public API.  All public symbols are re-exported here
so that ``from brain_alpha_ops.research.assistant import build_assistant_request_pack``
continues to work unchanged.

Sub-modules:
  - ``_constants`` : schema versions, ASSISTANT_RESPONSE_SCHEMA, logger
  - ``_helpers``   : pure utility functions (``_as_dict``, ``_clamp``, ...)
  - ``request``    : build_assistant_request_pack, render_assistant_request_prompt,
                     prompt diagnostics / budgeting helpers
  - ``offline``    : build_offline_assistant_response, _offline_summary,
                     _offline_confidence
  - ``response``   : parse_assistant_response, assistant_response_to_generation_guidance,
                     _normalize_assistant_response, _normalize_adjustments
"""

from __future__ import annotations

from brain_alpha_ops.research.assistant_json import AssistantResponseParseError
from brain_alpha_ops.research.assistant_json import (
    extract_json_payload as _extract_json_payload,
)

from ._constants import (
    ASSISTANT_GUIDANCE_SCHEMA_VERSION,
    ASSISTANT_REQUEST_SCHEMA_VERSION,
    ASSISTANT_RESPONSE_SCHEMA,
    ASSISTANT_RESPONSE_SCHEMA_VERSION,
    DEFAULT_MAX_PROMPT_TOKENS,
    INTERNAL_CONTEXT_METADATA_KEYS,
    logger,
)
from ._helpers import (
    _as_dict,
    _clamp,
    _digest_json,
    _digest_text,
    _duplicate_expressions,
    _float_value,
    _guidance_count,
    _guidance_digest,
    _guidance_outcomes,
    _guidance_success_rate,
    _int_value,
    _normalize_confidence,
    _number_items,
    _recent_backtest_records,
    _string_items,
    _strong_guidance_outcome,
    _unique_numbers,
    _unique_strings,
    _weak_guidance_outcome,
)
from .offline import (
    _offline_confidence,
    _offline_summary,
    build_offline_assistant_response,
)
from .request import (
    _assistant_prompt_diagnostics,
    _budgeted_context,
    _compact_context_lists,
    _estimated_tokens,
    _strip_internal_context_metadata,
    build_assistant_request_pack,
    render_assistant_request_prompt,
)
from .response import (
    _normalize_adjustments,
    _normalize_assistant_response,
    assistant_response_to_generation_guidance,
    parse_assistant_response,
)

__all__ = [
    # Constants
    "ASSISTANT_REQUEST_SCHEMA_VERSION",
    "ASSISTANT_RESPONSE_SCHEMA_VERSION",
    "ASSISTANT_GUIDANCE_SCHEMA_VERSION",
    "DEFAULT_MAX_PROMPT_TOKENS",
    "INTERNAL_CONTEXT_METADATA_KEYS",
    "ASSISTANT_RESPONSE_SCHEMA",
    "logger",
    # Public API
    "AssistantResponseParseError",
    "build_assistant_request_pack",
    "render_assistant_request_prompt",
    "build_offline_assistant_response",
    "parse_assistant_response",
    "assistant_response_to_generation_guidance",
    # Private helpers (re-exported for backward compatibility / monkeypatch)
    "_extract_json_payload",
    "_normalize_assistant_response",
    "_normalize_adjustments",
    "_assistant_prompt_diagnostics",
    "_budgeted_context",
    "_compact_context_lists",
    "_estimated_tokens",
    "_strip_internal_context_metadata",
    "_offline_summary",
    "_offline_confidence",
    "_unique_strings",
    "_string_items",
    "_number_items",
    "_unique_numbers",
    "_normalize_confidence",
    "_as_dict",
    "_guidance_outcomes",
    "_strong_guidance_outcome",
    "_weak_guidance_outcome",
    "_duplicate_expressions",
    "_recent_backtest_records",
    "_guidance_digest",
    "_guidance_count",
    "_guidance_success_rate",
    "_int_value",
    "_float_value",
    "_clamp",
    "_digest_text",
    "_digest_json",
]
