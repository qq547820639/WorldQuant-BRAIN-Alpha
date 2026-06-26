"""Re-export from the ``official_helpers`` subpackage for backward compatibility."""

from __future__ import annotations

import logging

from ._url import (
    ALLOWED_OFFICIAL_API_HOSTS,
    RESERVED_OFFLINE_TEST_HOST_SUFFIXES,
    _validate_official_api_origin,
    build_official_url,
    looks_non_production_alpha_id,
    parse_response,
    retry_after,
    retry_delay,
    retryable_status,
)
from ._normalize import (
    _find_all,
    _first_value,
    _num,
    _num_or_none,
    _ratio,
    build_simulation_payload,
    merge_payloads,
    normal_alpha,
    normal_data_category,
    normal_dataset,
    normal_field,
    normal_operator,
    normalize_metrics,
    scrub,
)
from ._pagination import (
    _positive_int,
    dedupe_alpha_items,
    is_user_alpha_offset_limit,
    items,
    looks_partial_context_cache,
    oldest_alpha_created_at,
    page_signature,
    total_count,
    user_alpha_cursor_recovery,
    user_alpha_offset_recovery,
    user_alpha_progress,
)

_logger = logging.getLogger("brain_alpha_ops.brain_api.official_helpers")

__all__ = [
    "ALLOWED_OFFICIAL_API_HOSTS",
    "RESERVED_OFFLINE_TEST_HOST_SUFFIXES",
    "build_official_url",
    "build_simulation_payload",
    "normalize_metrics",
    "normal_field",
    "normal_operator",
    "normal_dataset",
    "normal_data_category",
    "normal_alpha",
    "looks_non_production_alpha_id",
    "looks_partial_context_cache",
    "items",
    "total_count",
    "page_signature",
    "is_user_alpha_offset_limit",
    "oldest_alpha_created_at",
    "dedupe_alpha_items",
    "user_alpha_offset_recovery",
    "user_alpha_cursor_recovery",
    "user_alpha_progress",
    "retry_after",
    "retryable_status",
    "retry_delay",
    "parse_response",
    "merge_payloads",
    "scrub",
    "_first_value",
    "_find_all",
    "_positive_int",
    "_num",
    "_num_or_none",
    "_ratio",
    "_validate_official_api_origin",
    "_logger",
]
