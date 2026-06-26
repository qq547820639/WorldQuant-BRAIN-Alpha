"""Re-export from the ``convergence`` subpackage.

The original monolithic ``convergence.py`` was split into:
  - ``_stats``            : ``_inv_norm_cdf``, ``_bca_alpha``, ``_normal_cdf``
                            statistical helpers
  - ``_types``            : ``CycleRecord`` and ``ConvergenceStatus`` dataclasses
  - ``_bootstrap_mixin``  : ``_BootstrapMixin`` carrying ``_bootstrap_ci``
                            (BCa bootstrap confidence interval) and
                            ``_spearman_trend`` (Spearman rank trend)
  - ``_tracker``          : ``ConvergenceTracker`` class assembly

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.convergence import ConvergenceTracker``
continue to work, and re-exports the private helper symbols so tests
that monkeypatch ``brain_alpha_ops.research.convergence._xxx`` keep
functioning.
"""

from __future__ import annotations

from brain_alpha_ops.research.convergence._types import (  # noqa: F401
    ConvergenceStatus,
    CycleRecord,
)
from brain_alpha_ops.research.convergence._stats import (  # noqa: F401
    _bca_alpha,
    _inv_norm_cdf,
    _normal_cdf,
)
from brain_alpha_ops.research.convergence._bootstrap_mixin import (  # noqa: F401
    _BootstrapMixin,
)
from brain_alpha_ops.research.convergence._tracker import (  # noqa: F401
    ConvergenceTracker,
    logger,
)

__all__ = [
    # Data structures
    "CycleRecord",
    "ConvergenceStatus",
    "ConvergenceTracker",
    # Private symbols re-exported for test monkeypatch compatibility.
    "_BootstrapMixin",
    "_bca_alpha",
    "_inv_norm_cdf",
    "_normal_cdf",
    "logger",
]
