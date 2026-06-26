"""Cloud sync job service entry point.

Re-exports the public API of the original ``_service`` module after it was
split into focused submodules. The leading-underscore package name preserves
the monkeypatch path ``brain_alpha_ops.web_cloud.sync_job._service``.

Submodules:
  - ``_state``  : ``SyncJobContext`` holding shared mutable state and the
    heartbeat / cancellation / progress-callback helpers that were originally
    nested closures inside ``run_sync_job_service``.
  - ``_runner`` : the ``run_sync_job_service`` orchestration entry point.
"""

from __future__ import annotations

import logging

from ._runner import run_sync_job_service

# Preserve the original module-level logger attribute. The name is hardcoded
# to the original module path so log records still route to the same logger
# regardless of which submodule emits them.
logger = logging.getLogger("brain_alpha_ops.web_cloud.sync_job._service")

# Re-export the names that the original ``_service`` module imported from its
# siblings, so ``from brain_alpha_ops.web_cloud.sync_job._service import X``
# keeps working for any external (or test) code that relied on the surface.
from .._helpers import (  # noqa: E402,F401
    _SCAN_OBSERVABILITY_KEYS,
    _cloud_scan_status_message,
    _final_sync_status_message,
    _scan_observability,
    _sync_range_label,
    _timing_payload,
)
from .._types import (  # noqa: E402,F401
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
from ._state import SyncJobContext  # noqa: E402,F401

__all__ = [
    "run_sync_job_service",
    "logger",
    "SyncJobContext",
    # Type aliases re-exported for backward compatibility
    "ApiFromRunConfig",
    "DatasetsFromFields",
    "ErrorPayload",
    "JobStoreLike",
    "PersistOfficialContext",
    "RepositoryFactory",
    "RunConfigFromPayload",
    "SafeErrorMessage",
    "SyncJobCancelled",
    # Private helper re-exports for backward compatibility
    "_SCAN_OBSERVABILITY_KEYS",
    "_cloud_scan_status_message",
    "_final_sync_status_message",
    "_scan_observability",
    "_sync_range_label",
    "_timing_payload",
]
