"""Data model and constants for the ``IterativeOptimizer`` subpackage.

Extracted from the original ``iterative_optimizer.py`` monolith. Holds the
``MutationResult`` dataclass plus the operator family / structure wrap /
default window constants used by the directed mutation strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════════════
# Operator family grouping based on BRAIN operator semantics.
# ═══════════════════════════════════════════════════════════════════════

_OPERATOR_FAMILIES: dict[str, list[str]] = {
    "ranking":       ["ts_rank", "rank", "group_rank"],
    "standardization": ["zscore", "scale", "group_zscore"],
    "moving_average":  ["ts_mean", "ts_sum", "ts_product", "ts_arg_max", "ts_arg_min"],
    "difference":      ["ts_delta", "ts_av_diff"],
    "volatility":      ["ts_std_dev", "ts_skewness", "ts_kurtosis"],
    "correlation":     ["ts_corr", "ts_covariance"],
    "winsorization":   ["winsorize"],
    "decay":           ["ts_decay_linear"],
    "step":            ["ts_step"],
    "minmax":          ["ts_min", "ts_max"],
}

# Alternative operators per family, used by operator_substitute.
_STRUCTURE_WRAPS: list[str] = ["winsorize", "zscore", "scale"]


# ═══════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MutationResult:
    """Result of a single mutation."""
    expression: str
    mode: str                        # field_swap | window_perturb | structure_refine | operator_substitute
    reason: str                      # Why this mutation was chosen.
    parent_failure: str              # Original failure dimension.
    metadata: dict[str, Any] = field(default_factory=dict)


# Default window candidates used by the standalone ``window_perturb_expression``
# helper when no IterativeOptimizer instance is supplied.
_DEFAULT_WINDOWS = [3, 5, 8, 10, 12, 15, 20, 30, 40, 60, 90, 120, 180, 252]
