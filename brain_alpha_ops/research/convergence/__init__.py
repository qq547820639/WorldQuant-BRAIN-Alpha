"""Re-export from the ``convergence`` subpackage.

The original monolithic ``convergence.py`` was consolidated into:
  - ``bootstrap`` : ``CycleRecord`` and ``ConvergenceStatus`` dataclasses,
                    ``_inv_norm_cdf`` / ``_bca_alpha`` / ``_normal_cdf``
                    statistical helpers, and ``_BootstrapMixin`` carrying
                    ``_bootstrap_ci`` (BCa bootstrap confidence interval)
                    and ``_spearman_trend`` (Spearman rank trend)
  - ``tracker``   : ``ConvergenceTracker`` class assembly and ``logger``

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.convergence import ConvergenceTracker``
continue to work, and re-exports the private helper symbols so tests
that monkeypatch ``brain_alpha_ops.research.convergence._xxx`` keep
functioning.
"""

from __future__ import annotations

from .bootstrap import (  # noqa: F401
    ConvergenceStatus,
    CycleRecord,
    _BootstrapMixin,
    _bca_alpha,
    _inv_norm_cdf,
    _normal_cdf,
)
from .tracker import (  # noqa: F401
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
