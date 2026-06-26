"""BRAIN official Alpha Checks — registry classes.

``AlphaCheck`` and ``AlphaCheckRegistry`` originally defined in
``alpha_checks.py``.
"""
from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.research.alpha_checks._types import CheckResult, CheckReport
from brain_alpha_ops.research.alpha_checks._checks_basic import (
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
)
from brain_alpha_ops.research.alpha_checks._checks_advanced import (
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


class AlphaCheck:
    """A single alpha quality check."""

    def __init__(
        self,
        name: str,
        check_fn: Callable[[dict[str, Any]], CheckResult],
        severity: str = "ERROR",
    ) -> None:
        self.name = name
        self._check_fn = check_fn
        self.severity = severity

    def run(self, sim_result: dict[str, Any]) -> CheckResult:
        result = self._check_fn(sim_result)
        result.severity = self.severity
        return result


class AlphaCheckRegistry:
    """Registry of all BRAIN official alpha checks.

    Usage::

        registry = AlphaCheckRegistry()
        registry.build_default_checks()
        report = registry.evaluate(sim_result)
        if report.passed:
            print("Alpha passed all checks")
    """

    def __init__(self) -> None:
        self._checks: dict[str, AlphaCheck] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, check: AlphaCheck) -> None:
        self._checks[check.name] = check

    def get(self, name: str) -> AlphaCheck | None:
        return self._checks.get(name)

    def get_all(self) -> list[AlphaCheck]:
        return list(self._checks.values())

    def get_by_severity(self, severity: str) -> list[AlphaCheck]:
        return [c for c in self._checks.values() if c.severity == severity]

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------
    def evaluate(
        self,
        sim_result: dict[str, Any],
        checks: list[str] | None = None,
    ) -> CheckReport:
        """Run specified checks (all by default) against *sim_result*."""
        if checks is None:
            checks = list(self._checks.keys())

        report = CheckReport()
        for name in checks:
            check = self._checks.get(name)
            if check is None:
                continue
            result = check.run(sim_result)
            report.results.append(result)
            report.total += 1
            if result.passed:
                report.passed_count += 1
            else:
                report.failed_count += 1
                if result.severity == "ERROR":
                    report.passed = False

        report.summary = (
            f"{report.passed_count}/{report.total} passed"
            + (f", {report.failed_count} FAILED" if report.failed_count else "")
        )
        return report

    # ------------------------------------------------------------------
    # Build default checks (from BRAIN official standards)
    # ------------------------------------------------------------------
    def build_default_checks(self) -> None:
        """Register all BRAIN-standard checks."""

        # --- Core performance metrics ---
        self.register(AlphaCheck("sharpe_positive", _check_sharpe_positive, "ERROR"))
        self.register(AlphaCheck("fitness_minimum", _check_fitness_minimum, "ERROR"))
        self.register(AlphaCheck("returns_positive", _check_returns_positive, "WARNING"))
        self.register(AlphaCheck("drawdown_limit", _check_drawdown_limit, "WARNING"))

        # --- Turnover (platform and quality layers) ---
        self.register(AlphaCheck("turnover_platform", _check_turnover_platform, "ERROR"))
        self.register(AlphaCheck("turnover_quality", _check_turnover_quality, "ERROR"))

        # --- Correlation checks ---
        self.register(AlphaCheck("self_correlation", _check_self_correlation, "ERROR"))
        self.register(AlphaCheck("prod_correlation", _check_prod_correlation, "ERROR"))

        # --- Concentration ---
        self.register(AlphaCheck("weight_concentration", _check_weight_concentration, "ERROR"))

        # --- Sub-universe Sharpe (BRAIN: LOW_SUB_UNIVERSE_SHARPE) ---
        self.register(AlphaCheck("sub_universe_sharpe", _check_sub_universe_sharpe, "ERROR"))

        # --- Risk ---
        self.register(AlphaCheck("marginal_contribution", _check_marginal_contribution, "WARNING"))

        # --- Margin (BRAIN advisor target, not a platform hard check) ---
        self.register(AlphaCheck("margin_minimum", _check_margin_minimum, "WARNING"))

        # --- IC checks ---
        self.register(AlphaCheck("ic_mean", _check_ic_mean, "WARNING"))
        self.register(AlphaCheck("ic_ir", _check_ic_ir, "WARNING"))
        self.register(AlphaCheck("rank_ic", _check_rank_ic, "INFO"))

        # --- Stability ---
        self.register(AlphaCheck("turnover_stability", _check_turnover_stability, "INFO"))
        self.register(AlphaCheck("drawdown_stability", _check_drawdown_stability, "INFO"))

        # --- Universe coverage ---
        self.register(AlphaCheck("coverage_minimum", _check_coverage_minimum, "WARNING"))

        # --- Structure ---
        self.register(AlphaCheck("expression_valid", _check_expression_valid, "ERROR"))
        self.register(AlphaCheck("neutralization_applied", _check_neutralization, "INFO"))
        self.register(AlphaCheck("pasteurization_applied", _check_pasteurization, "INFO"))

        # --- Data compliance ---
        self.register(AlphaCheck("delay_consistent", _check_delay_consistent, "WARNING"))
        self.register(AlphaCheck("nan_handling", _check_nan_handling, "INFO"))

        # --- P1-3: IS/OOS robustness ---
        self.register(AlphaCheck("is_oos_robustness", _check_is_oos_robustness, "WARNING"))

        # --- P2-1: Expression complexity ---
        self.register(AlphaCheck("expression_complexity", _check_expression_complexity, "INFO"))

    # ------------------------------------------------------------------
    # P1-5: Type-specific checks (POWER_POOL, ATOM, PYRAMID)
    # ------------------------------------------------------------------
    def build_type_checks(self, alpha_type: str) -> None:
        """Register additional checks specific to an alpha type."""
        if alpha_type == "POWER_POOL":
            self.register(AlphaCheck("powerpool_sharpe", _check_powerpool_sharpe, "ERROR"))
            self.register(AlphaCheck("powerpool_operators", _check_powerpool_operators, "ERROR"))
            self.register(AlphaCheck("powerpool_fields", _check_powerpool_fields, "ERROR"))
            self.register(AlphaCheck("powerpool_self_corr", _check_powerpool_self_corr, "ERROR"))
            self.register(AlphaCheck("powerpool_region_delay", _check_powerpool_region_delay, "ERROR"))
        elif alpha_type == "ATOM":
            self.register(AlphaCheck("atom_single_dataset", _check_atom_single_dataset, "ERROR"))
        elif alpha_type == "PYRAMID":
            self.register(AlphaCheck("pyramid_count", _check_pyramid_count, "WARNING"))
