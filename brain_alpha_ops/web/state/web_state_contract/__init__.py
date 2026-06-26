"""Shared Web state and user-error contract helpers.

The Web console has several independently polled workflows.  This module keeps
their browser-facing status and recovery hints consistent without changing the
existing raw job/error fields that older callers already consume.

Subpackage split (formerly ``web_state_contract.py`` monolith):
  - ``_definitions``  : error catalogue + status label/set constants
  - ``_classification``: status and user-error kind classification helpers
  - ``_contract``     : public enrichment / user-error builder functions
"""
from __future__ import annotations

from ._definitions import (
    _CANCELLED_STATUSES,
    _ERROR_DEFINITIONS,
    _FAILED_STATUSES,
    _MISSING_STATUSES,
    _STATUS_LABELS,
    _SUCCESS_STATUSES,
    _WARNING_STATUSES,
)
from ._classification import (
    _int_value,
    _looks_interrupted,
    _normalize_status,
    _specific_failed_job_kind,
    _state,
    classify_job_status,
    classify_user_error_kind,
)
from ._contract import (
    build_user_error,
    enrich_error_payload,
    enrich_job_response,
)

__all__ = [
    # Public API
    "build_user_error",
    "classify_job_status",
    "classify_user_error_kind",
    "enrich_error_payload",
    "enrich_job_response",
    # Private symbols re-exported for monkeypatch compatibility
    "_CANCELLED_STATUSES",
    "_ERROR_DEFINITIONS",
    "_FAILED_STATUSES",
    "_MISSING_STATUSES",
    "_STATUS_LABELS",
    "_SUCCESS_STATUSES",
    "_WARNING_STATUSES",
    "_int_value",
    "_looks_interrupted",
    "_normalize_status",
    "_specific_failed_job_kind",
    "_state",
]
