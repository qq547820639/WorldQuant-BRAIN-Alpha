"""Re-export from the ``pipeline_candidates`` subpackage.

The original monolithic ``pipeline_candidates.py`` was split into:
  - ``_local_prefilter``        : ``_LocalPrefilterMixin`` carrying
    ``_local_prefilter`` / ``_apply_local_backtest_prefilter`` /
    ``_apply_generation_field_prefilter`` / ``_record_local_backtest_knowledge``,
    plus the module-level helpers ``_safe_float`` and
    ``_local_backtest_failure_category`` and the package ``logger``
  - ``_pool_management``        : ``_CandidatePoolManagementMixin`` carrying
    pool top-up, merge/prune, validation target/quota planning, backtest
    slot selection, and pending candidate bookkeeping methods
  - ``_official_context_mixin`` : ``_OfficialContextMixin`` carrying context
    validation cache refresh, active dataset field resolution, and
    official context reason computation
  - ``_cloud_risk_mixin``       : ``_CloudRiskMixin`` carrying cloud
    similarity index refresh, correlation risk caching, high-similarity
    rejection, cloud status, accepted-candidate remembering, and smart
    ranking helpers
  - ``_class``                  : ``PipelineCandidatePoolMixin`` class assembly

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.pipeline_candidates import ...``
continue to work.
"""

from __future__ import annotations

from brain_alpha_ops.research.pipeline_candidates._class import (  # noqa: F401
    PipelineCandidatePoolMixin,
)
from brain_alpha_ops.research.pipeline_candidates._local_prefilter import (  # noqa: F401
    _local_backtest_failure_category,
    _safe_float,
    logger,
)

__all__ = [
    # Public API
    "PipelineCandidatePoolMixin",
    # Module-level logger (preserved for caplog/monkeypatch compatibility)
    "logger",
    # Private helpers (re-exported for test monkeypatch compatibility)
    "_local_backtest_failure_category",
    "_safe_float",
]
