"""Re-export from the ``iterative_optimizer`` subpackage.

The original monolithic ``iterative_optimizer.py`` was consolidated into:
  - ``optimizer``  : ``MutationResult`` dataclass, ``_OPERATOR_FAMILIES`` /
                     ``_DEFAULT_WINDOWS`` constants, loader/json introspection
                     helpers (``_current_official_operator_names``,
                     ``_operator_names_from_loader``, ``logger``), the
                     ``IterativeOptimizer`` class assembly, and the standalone
                     ``window_perturb_expression`` /
                     ``operator_substitute_expression`` /
                     ``structure_refine_expression`` helpers
  - ``mutations``  : ``_STRUCTURE_WRAPS`` constant and ``_MutationsMixin``
                     carrying the five mutation operators

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.iterative_optimizer import ...``
continue to work, and re-exports the private helper symbols so tests that
monkeypatch ``brain_alpha_ops.research.iterative_optimizer._xxx`` keep
functioning.
"""

from __future__ import annotations

from .optimizer import (  # noqa: F401
    IterativeOptimizer,
    MutationResult,
    _DEFAULT_WINDOWS,
    _OPERATOR_FAMILIES,
    _current_official_operator_names,
    _operator_names_from_loader,
    logger,
    operator_substitute_expression,
    structure_refine_expression,
    window_perturb_expression,
)
from .mutations import (  # noqa: F401
    _STRUCTURE_WRAPS,
    _MutationsMixin,
)

__all__ = [
    # Data structures / constants
    "MutationResult",
    "IterativeOptimizer",
    # Standalone helpers
    "window_perturb_expression",
    "operator_substitute_expression",
    "structure_refine_expression",
    # Private symbols re-exported for test monkeypatch compatibility.
    "_DEFAULT_WINDOWS",
    "_OPERATOR_FAMILIES",
    "_STRUCTURE_WRAPS",
    "_MutationsMixin",
    "_current_official_operator_names",
    "_operator_names_from_loader",
    "logger",
]
