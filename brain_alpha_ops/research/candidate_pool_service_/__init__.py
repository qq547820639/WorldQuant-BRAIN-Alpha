"""Re-export from the ``candidate_pool_service_`` subpackage.

The original monolithic ``candidate_pool_service_.py`` was split into:
  - ``_helpers``         : module-level ``logger`` (hardcoded name) plus the
                           private free functions ``_local_backtest_failure_category``
                           and ``_safe_float``
  - ``_local_prefilter`` : ``_LocalPrefilterMixin`` carrying ``_local_prefilter``,
                           ``_apply_local_backtest_prefilter``,
                           ``_apply_generation_field_prefilter`` and
                           ``_record_local_backtest_knowledge``
  - ``_pool_ops``        : ``_PoolOpsMixin`` carrying ``_top_up_candidate_pool``,
                           the official-context refresh helpers, and the thin
                           pool-delegation wrappers
  - ``_cloud_risk``      : ``_CloudRiskMixin`` carrying the cloud-similarity
                           cache, the pre-official high-similarity rejection
                           gate, and the smart-ranking wrappers
  - ``_service``         : ``CandidatePoolService_`` class assembly that mixes
                           in the three responsibility mixins

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.candidate_pool_service_ import ...``
continue to work.
"""

from __future__ import annotations

from brain_alpha_ops.research.candidate_pool_service_._helpers import (  # noqa: F401
    _local_backtest_failure_category,
    _safe_float,
    logger,
)
from brain_alpha_ops.research.candidate_pool_service_._local_prefilter import (  # noqa: F401
    _LocalPrefilterMixin,
)
from brain_alpha_ops.research.candidate_pool_service_._pool_ops import (  # noqa: F401
    _PoolOpsMixin,
)
from brain_alpha_ops.research.candidate_pool_service_._cloud_risk import (  # noqa: F401
    _CloudRiskMixin,
)
from brain_alpha_ops.research.candidate_pool_service_._service import (  # noqa: F401
    CandidatePoolService_,
)

__all__ = [
    # Public API
    "CandidatePoolService_",
    "logger",
    # Private helpers (re-exported for test monkeypatch compatibility)
    "_LocalPrefilterMixin",
    "_PoolOpsMixin",
    "_CloudRiskMixin",
    "_local_backtest_failure_category",
    "_safe_float",
]
