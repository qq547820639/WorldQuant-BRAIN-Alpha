"""Shared constants, type aliases, and helpers for the snapshot subpackage."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.runtime_constants import CloudDefaults

logger = logging.getLogger(__name__)

# ── Centralized constants (source of truth: runtime_constants.py) ──
CLOUD_SYNC_STALE_SECONDS = CloudDefaults.CLOUD_SYNC_STALE_SECONDS
CONTEXT_CACHE_MANIFEST_SCHEMA = CloudDefaults.CONTEXT_CACHE_MANIFEST_SCHEMA
OFFICIAL_CONTEXT_FILES = (
    ("fields_count", "official_fields.json"),
    ("operators_count", "official_operators.json"),
    ("datasets_count", "official_datasets.json"),
)

LoadConfig = Callable[[], Any]
RuntimeRoot = Callable[[], Path]
SafeErrorMessage = Callable[[Exception], str]


def _safe_error_message(exc: Exception) -> str:
    return redact_error_message(exc)
