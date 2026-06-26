"""Re-export from the ``alpha_checks`` subpackage for backward compatibility.

The original monolithic ``alpha_checks.py`` was split into the
``brain_alpha_ops.research.alpha_checks`` subpackage. This module re-exports
the full public API surface so legacy imports continue to work.

Sub-modules:
  - ``_types``           : ``CheckResult``, ``CheckReport`` dataclasses
  - ``_registry``        : ``AlphaCheck``, ``AlphaCheckRegistry`` classes
  - ``_checks_basic``    : core BRAIN check functions (sharpe, fitness,
                           turnover, correlation, etc.)
  - ``_checks_advanced`` : type-specific + IS/OOS + complexity checks
"""
from __future__ import annotations

# Re-export everything from sub-modules
from brain_alpha_ops.research.alpha_checks._types import (  # noqa: F401
    CheckReport,
    CheckResult,
)
from brain_alpha_ops.research.alpha_checks._registry import (  # noqa: F401
    AlphaCheck,
    AlphaCheckRegistry,
)
from brain_alpha_ops.research.alpha_checks._checks_basic import (  # noqa: F401
    _check_drawdown_limit,
    _check_fitness_minimum,
    _check_margin_minimum,
    _check_marginal_contribution,
    _check_prod_correlation,
    _check_returns_positive,
    _check_self_correlation,
    _check_sharpe_positive,
    _check_sub_universe_sharpe,
    _check_turnover_platform,
    _check_turnover_quality,
    _check_weight_concentration,
    _metric,
)
from brain_alpha_ops.research.alpha_checks._checks_advanced import (  # noqa: F401
    _check_atom_single_dataset,
    _check_coverage_minimum,
    _check_delay_consistent,
    _check_drawdown_stability,
    _check_expression_complexity,
    _check_expression_valid,
    _check_ic_ir,
    _check_ic_mean,
    _check_is_oos_robustness,
    _check_nan_handling,
    _check_neutralization,
    _check_pasteurization,
    _check_powerpool_fields,
    _check_powerpool_operators,
    _check_powerpool_region_delay,
    _check_powerpool_self_corr,
    _check_powerpool_sharpe,
    _check_pyramid_count,
    _check_rank_ic,
    _check_turnover_stability,
)

__all__ = [
    # Data structures
    "CheckResult",
    "CheckReport",
    # Registry classes
    "AlphaCheck",
    "AlphaCheckRegistry",
    # Basic checks
    "_metric",
    "_check_sharpe_positive",
    "_check_fitness_minimum",
    "_check_returns_positive",
    "_check_drawdown_limit",
    "_check_turnover_platform",
    "_check_turnover_quality",
    "_check_self_correlation",
    "_check_prod_correlation",
    "_check_weight_concentration",
    "_check_sub_universe_sharpe",
    "_check_marginal_contribution",
    "_check_margin_minimum",
    # Advanced checks
    "_check_ic_mean",
    "_check_ic_ir",
    "_check_rank_ic",
    "_check_turnover_stability",
    "_check_drawdown_stability",
    "_check_coverage_minimum",
    "_check_expression_valid",
    "_check_neutralization",
    "_check_pasteurization",
    "_check_delay_consistent",
    "_check_nan_handling",
    "_check_powerpool_sharpe",
    "_check_powerpool_operators",
    "_check_powerpool_fields",
    "_check_powerpool_self_corr",
    "_check_powerpool_region_delay",
    "_check_atom_single_dataset",
    "_check_pyramid_count",
    "_check_is_oos_robustness",
    "_check_expression_complexity",
]
