"""Re-export from the ``iterative_optimizer`` subpackage.

The original monolithic ``iterative_optimizer.py`` was split into:
  - ``_helpers``          : ``_current_official_operator_names`` and
                            ``_operator_names_from_loader`` (loader/json
                            introspection helpers)
  - ``_types``            : ``MutationResult`` dataclass + the
                            ``_OPERATOR_FAMILIES`` / ``_STRUCTURE_WRAPS`` /
                            ``_DEFAULT_WINDOWS`` constants
  - ``_mutations_mixin``  : ``_MutationsMixin`` carrying the five mutation
                            operators (``field_swap``,
                            ``field_swap_semantic``, ``window_perturb``,
                            ``structure_refine``, ``operator_substitute``)
                            and the ``_safe_replace_token`` helper
  - ``_optimizer``        : ``IterativeOptimizer`` class assembly
  - ``_standalone``       : standalone ``window_perturb_expression`` /
                            ``operator_substitute_expression`` /
                            ``structure_refine_expression`` helpers

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.iterative_optimizer import ...``
continue to work, and re-exports the private helper symbols so tests that
monkeypatch ``brain_alpha_ops.research.iterative_optimizer._xxx`` keep
functioning.
"""

from __future__ import annotations

from brain_alpha_ops.research.iterative_optimizer._types import (  # noqa: F401
    MutationResult,
    _DEFAULT_WINDOWS,
    _OPERATOR_FAMILIES,
    _STRUCTURE_WRAPS,
)
from brain_alpha_ops.research.iterative_optimizer._helpers import (  # noqa: F401
    _current_official_operator_names,
    _operator_names_from_loader,
    logger,
)
from brain_alpha_ops.research.iterative_optimizer._mutations_mixin import (  # noqa: F401
    _MutationsMixin,
)
from brain_alpha_ops.research.iterative_optimizer._optimizer import (  # noqa: F401
    IterativeOptimizer,
)
from brain_alpha_ops.research.iterative_optimizer._standalone import (  # noqa: F401
    operator_substitute_expression,
    structure_refine_expression,
    window_perturb_expression,
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
