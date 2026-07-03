"""Re-export from the ``pipeline_candidates`` subpackage.

The original monolithic ``pipeline_candidates.py`` was split (and now
re-consolidated) into:
  - ``pipeline_candidates``        : ``PipelineCandidatePoolMixin`` class
    assembly plus ``_LocalPrefilterMixin`` (local scoring, backtest
    prefilter, generation-field prefilter, local-backtest knowledge
    recording) and ``_CandidatePoolManagementMixin`` (pool top-up,
    merge/prune, validation target/quota planning, backtest slot
    selection, pending candidate bookkeeping). Also defines the package
    ``logger`` and module-level helpers ``_safe_float`` and
    ``_local_backtest_failure_category``
  - ``pipeline_candidates_mixins`` : ``_OfficialContextMixin`` (context
    validation cache refresh, active dataset field resolution, official
    context reason computation) and ``_CloudRiskMixin`` (cloud similarity
    index refresh, correlation risk caching, high-similarity rejection,
    cloud status, accepted-candidate remembering, smart ranking helpers)

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.pipeline_candidates import ...``
continue to work.
"""

from __future__ import annotations

from .pipeline_candidates import (  # noqa: F401
    PipelineCandidatePoolMixin,
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
