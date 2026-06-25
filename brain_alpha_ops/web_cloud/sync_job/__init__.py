"""Cloud sync jobs and payload builders.

Subpackage of ``brain_alpha_ops.web_cloud``. Splits the original
``sync_job.py`` monolith into focused modules while preserving the public
API surface via re-exports.

  - ``_types``   : protocols, exception, and callable type aliases
  - ``_helpers`` : timing / observability helpers and status messages
  - ``_service`` : ``run_sync_job_service`` orchestration entry point
"""

from __future__ import annotations

from ._types import (
    ApiFromRunConfig,
    DatasetsFromFields,
    ErrorPayload,
    JobStoreLike,
    PersistOfficialContext,
    RepositoryFactory,
    RunConfigFromPayload,
    SafeErrorMessage,
    SyncJobCancelled,
)
from ._helpers import (
    _SCAN_OBSERVABILITY_BOOL_KEYS,
    _SCAN_OBSERVABILITY_FLOAT_KEYS,
    _SCAN_OBSERVABILITY_INT_KEYS,
    _SCAN_OBSERVABILITY_KEYS,
    _SCAN_OBSERVABILITY_TEXT_KEYS,
    _cloud_scan_status_message,
    _final_sync_status_message,
    _scan_observability,
    _sync_range_label,
    _timing_payload,
)
from ._service import run_sync_job_service

# Backward-compat re-export (original sync_job.py trailing import).
from ..snapshot import path_modified_at  # noqa: F401

__all__ = [
    # Types
    "JobStoreLike",
    "SyncJobCancelled",
    "ApiFromRunConfig",
    "DatasetsFromFields",
    "ErrorPayload",
    "PersistOfficialContext",
    "RepositoryFactory",
    "RunConfigFromPayload",
    "SafeErrorMessage",
    # Public API
    "run_sync_job_service",
    "path_modified_at",
    # Private helpers (re-exported for backward compatibility)
    "_timing_payload",
    "_scan_observability",
    "_cloud_scan_status_message",
    "_sync_range_label",
    "_final_sync_status_message",
    "_SCAN_OBSERVABILITY_INT_KEYS",
    "_SCAN_OBSERVABILITY_FLOAT_KEYS",
    "_SCAN_OBSERVABILITY_TEXT_KEYS",
    "_SCAN_OBSERVABILITY_BOOL_KEYS",
    "_SCAN_OBSERVABILITY_KEYS",
]
