"""BRAIN official Alpha Checks — 20+ standard checks sourced from BRAIN API docs.

Replaces fictional metrics (min_total_score, min_sub_universe_sharpe_ratio,
min_margin_bps) with real BRAIN platform checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CheckResult:
    """Result of a single alpha check."""
    check_name: str
    passed: bool
    actual: Any = None
    expected: str = ""
    severity: str = "ERROR"       # ERROR | WARNING | INFO
    message: str = ""
    exception_applied: bool = False  # True when BRAIN exception rule was applied (e.g. SELF_CORRELATION Sharpe advantage)


@dataclass
class CheckReport:
    """Aggregate report of all alpha checks."""
    passed: bool = True
    total: int = 0
    passed_count: int = 0
    failed_count: int = 0
    results: list[CheckResult] = field(default_factory=list)
    summary: str = ""


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


# ======================================================================
# Individual check implementations
# ======================================================================

def _metric(sim: dict[str, Any], *keys: str, default: Any = 0.0) -> float:
    """Extract a numeric metric from sim result, trying multiple keys."""
    for key in keys:
        val = sim.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return float(default)


def _check_sharpe_positive(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "sharpe", "Sharpe")
    thresholds = sim.get("_thresholds", None)
    settings = sim.get("settings", {}) or {}
    delay = int(settings.get("delay", 1))
    # BRAIN: LOW_SHARPE threshold depends on delay
    if delay == 0:
        min_sharpe = float(getattr(thresholds, "min_sharpe_delay0", 2.0))
    else:
        min_sharpe = float(getattr(thresholds, "min_sharpe", 1.25))
    passed = val >= min_sharpe
    return CheckResult(
        check_name="sharpe_positive",
        passed=passed,
        actual=val,
        expected=f">= {min_sharpe} (Delay-{delay})",
        message=f"Sharpe={val:.3f}" + ("" if passed else f" (below {min_sharpe})"),
    )


def _check_fitness_minimum(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "fitness", "Fitness")
    thresholds = sim.get("_thresholds", None)
    settings = sim.get("settings", {}) or {}
    delay = int(settings.get("delay", 1))
    # BRAIN: LOW_FITNESS threshold depends on delay
    if delay == 0:
        min_fitness = float(getattr(thresholds, "min_fitness_delay0", 1.3))
    else:
        min_fitness = float(getattr(thresholds, "min_fitness", 1.0))
    passed = val >= min_fitness
    return CheckResult(
        check_name="fitness_minimum",
        passed=passed,
        actual=val,
        expected=f">= {min_fitness} (Delay-{delay})",
        message=f"Fitness={val:.3f}" + ("" if passed else f" (below {min_fitness})"),
    )


def _check_returns_positive(sim: dict[str, Any]) -> CheckResult:
    """Qualitative check — BRAIN does not hard-check returns."""
    val = _metric(sim, "returns", "Returns", "return")
    passed = val > 0
    return CheckResult(
        check_name="returns_positive",
        passed=passed,
        actual=val,
        expected="> 0",
        message=f"Returns={val:.5f}" + ("" if passed else " (not positive)"),
    )


def _check_drawdown_limit(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: drawdown is NOT a hard platform check — qualitative guidance (WARNING).

    Uses max_drawdown from QualityThresholds (default 0.25).
    """
    val = abs(_metric(sim, "drawdown", "maxDrawdown", "MaxDrawdown"))
    thresholds = sim.get("_thresholds", None)
    max_drawdown = float(getattr(thresholds, "max_drawdown", 0.25))
    passed = val <= max_drawdown
    return CheckResult(
        check_name="drawdown_limit",
        passed=passed,
        actual=val,
        expected=f"<= {max_drawdown:.2f}",
        message=f"Drawdown={val:.3f}" + ("" if passed else f" (exceeds {max_drawdown:.2f}) — note: BRAIN does not hard-check drawdown"),
    )


def _check_turnover_platform(sim: dict[str, Any]) -> CheckResult:
    """BRAIN platform hard gate: turnover 1%-70% (LOW_TURNOVER / HIGH_TURNOVER).

    Source: BRAIN API Alpha Check — LOW_TURNOVER if < 1%, HIGH_TURNOVER if > 70%.
    This is the minimum compliance line for passing BRAIN checks and has ERROR
    severity.
    """
    val = _metric(sim, "turnover", "Turnover")
    thresholds = sim.get("_thresholds", None)
    min_t = float(getattr(thresholds, "min_turnover", 0.01))
    max_t = float(getattr(thresholds, "platform_max_turnover", 0.70))
    passed = min_t <= val <= max_t
    return CheckResult(
        check_name="turnover_platform",
        passed=passed,
        actual=val,
        expected=f"{min_t:.2f} – {max_t:.2f} (BRAIN platform hard gate)",
        message=f"Turnover={val:.3f}" + ("" if passed else f" (out of {min_t:.2f}–{max_t:.2f}) — BRAIN platform hard gate"),
    )


def _check_turnover_quality(sim: dict[str, Any]) -> CheckResult:
    """Advisor quality target: turnover < 30% for preferred submission.

    Alphas in the 30%-70% band are not hard-rejected, but should usually be
    optimized first by increasing decay, adding smoothing, extending lookback,
    or reducing trigger frequency. Prefer submitting alphas below 30% unless a
    30%-70% alpha is clearly stronger on Sharpe, Fitness, Drawdown, or
    correlation.

    Source: BRAIN advisor target — recommended turnover ceiling for robust
    alphas, WARNING severity.
    """
    val = _metric(sim, "turnover", "Turnover")
    thresholds = sim.get("_thresholds", None)
    target = float(getattr(thresholds, "target_max_turnover", 0.30))
    passed = val <= target
    return CheckResult(
        check_name="turnover_quality",
        passed=passed,
        actual=val,
        expected=f"<= {target:.2f} (preferred submission)",
        message=f"Turnover={val:.3f}" + ("" if passed else
            f" (>{target:.2f}) — optimize with higher decay, smoothing, longer lookback, or trade_when"),
    )


def _check_self_correlation(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: SELF_CORRELATION if >= 0.70 (PnL correlation with previously submitted alphas).

    Exception rule (BRAIN official): if new_alpha.Sharpe >= correlated_alpha.Sharpe × 1.10,
    the alpha can still be submitted even if correlation >= 0.70.
    """
    val = abs(_metric(sim, "selfCorrelation", "self_correlation", "correlation", default=0.0))
    passed = val < 0.70
    exception_applied = False

    # BRAIN exception: Sharpe advantage.
    if not passed:
        sharpe = _metric(sim, "sharpe", "Sharpe", default=0.0)
        related_sharpe = _metric(sim, "relatedAlphaSharpe", "related_alpha_sharpe", default=0.0)
        if related_sharpe > 0 and sharpe >= related_sharpe * 1.10:
            passed = True
            exception_applied = True

    expected_str = "< 0.70" if not exception_applied else "< 0.70 OR Sharpe >= related × 1.10"
    msg = f"SelfCorrelation={val:.4f}"
    if exception_applied:
        msg += " (exception: Sharpe advantage — new Sharpe >= related Sharpe × 1.10)"
    elif not passed:
        msg += " (>= 0.70)"

    return CheckResult(
        check_name="self_correlation",
        passed=passed,
        actual=val,
        expected=expected_str,
        message=msg,
        exception_applied=exception_applied,
    )


def _check_prod_correlation(sim: dict[str, Any]) -> CheckResult:
    val = abs(_metric(sim, "prodCorrelation", "prod_correlation", default=0.0))
    passed = val < 0.70  # BRAIN: SELF_CORRELATION applies to prod correlation too
    return CheckResult(
        check_name="prod_correlation",
        passed=passed,
        actual=val,
        expected="< 0.70",
        message=f"ProdCorrelation={val:.4f}" + ("" if passed else " (>= 0.70)"),
    )


def _check_weight_concentration(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "weightConcentration", "weight_concentration", "concentration", default=0.0)
    passed = val <= 0.10  # BRAIN: CONCENTRATED_WEIGHT if single stock > 10%
    return CheckResult(
        check_name="weight_concentration",
        passed=passed,
        actual=val,
        expected="<= 0.10",
        message=f"WeightConcentration={val:.4f}" + ("" if passed else " (exceeds 0.10)"),
    )


def _check_sub_universe_sharpe(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: LOW_SUB_UNIVERSE_SHARPE — sub_sharpe >= 0.75 × √(sub_size/alpha_size) × alpha_sharpe.

    Official formula: threshold = 0.75 × √(sub_size / alpha_size) × alpha_sharpe.
    When sub_size/alpha_size are unavailable from API, defaults to 1.0 (√1 = 1),
    which degenerates to the simple 0.75 × sharpe form.
    """
    import math
    sub_sharpe = _metric(sim, "subUniverseSharpe", "sub_universe_sharpe", default=0.0)
    sharpe = _metric(sim, "sharpe", "Sharpe", default=0.0)
    sub_size = _metric(sim, "subUniverseSize", "sub_size", default=1000)
    alpha_size = _metric(sim, "alphaSize", "alpha_size", default=1000)
    size_factor = math.sqrt(sub_size / max(alpha_size, 1))
    # Use configurable ratio (default 0.75) matching scoring.empirical_score formula
    thresholds = sim.get("_thresholds", None)
    ratio = float(getattr(thresholds, "sub_universe_sharpe_min_ratio", 0.75))
    threshold = ratio * size_factor * max(sharpe, 0.01)
    passed = sub_sharpe >= threshold
    exception_applied = False

    # BRAIN exception: LOW_SUB_UNIVERSE_SHARPE — when sub-universe is very small
    # (< 10% of alpha size), the check is downgraded from ERROR to WARNING
    # because the sub_universe is too small to produce reliable sub-sharpe metrics.
    # The BRAIN platform may still accept the alpha with this warning.
    low_sub_exception = not passed and sub_size > 0 and alpha_size > 0 and (sub_size / alpha_size) < 0.1
    if low_sub_exception:
        passed = True
        exception_applied = True

    expected_str = f">= {threshold:.4f} ({ratio}×√({sub_size:.0f}/{alpha_size:.0f})×sharpe)"
    if exception_applied:
        expected_str += " OR LOW_SUB_UNIVERSE_SHARPE exception (sub_size < 10% alpha_size)"
    msg = f"SubUniverseSharpe={sub_sharpe:.4f}"
    if exception_applied:
        msg += f" (LOW_SUB_UNIVERSE_SHARPE exception: sub_size={sub_size:.0f} < 0.1 × alpha_size={alpha_size:.0f})"
    elif not passed:
        msg += f" (below {threshold:.4f})"

    return CheckResult(
        check_name="sub_universe_sharpe",
        passed=passed,
        actual=sub_sharpe,
        expected=expected_str,
        message=msg,
        exception_applied=exception_applied,
    )


def _check_marginal_contribution(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: marginal contribution — not a named platform check; general risk."""
    val = _metric(sim, "marginalContribution", "marginal_contribution", default=0.0)
    passed = val > 0
    return CheckResult(
        check_name="marginal_contribution",
        passed=passed,
        actual=val,
        expected="> 0",
        message=f"MarginalContribution={val:.5f}",
    )


def _check_margin_minimum(sim: dict[str, Any]) -> CheckResult:
    """BRAIN advisor target: margin >= min_margin_bps (default 4.0 bps).

    Prefer API-returned margin field. Fall back to local estimation (returns/turnover/100)
    only when API does not provide the margin value.
    """
    # P2-3 / P0-4 fix: check whether the API supplied margin instead of default 0.0.
    api_margin = sim.get("margin") or sim.get("Margin")
    has_api_margin = api_margin is not None and (
        isinstance(api_margin, (int, float)) and abs(float(api_margin)) > 0.001
    )

    if has_api_margin:
        margin_bps = float(api_margin)
        margin_source = "BRAIN_API"
    else:
        returns = _metric(sim, "returns", "Returns", "return", default=0.0)
        turnover = _metric(sim, "turnover", "Turnover", default=0.01)
        margin_bps = (returns / max(turnover, 0.001)) / 100.0
        margin_source = "estimated"

    thresholds = sim.get("_thresholds", None)
    min_margin = float(getattr(thresholds, "min_margin_bps", 4.0))
    passed = margin_bps >= min_margin
    return CheckResult(
        check_name="margin_minimum",
        passed=passed,
        actual=round(margin_bps, 4),
        expected=f">= {min_margin:.1f} bps",
        message=f"Margin={margin_bps:.4f} bps [{margin_source}]" + ("" if passed else f" (below {min_margin:.1f} bps)"),
    )


def _check_ic_mean(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: IC Mean signal quality — |IC| >= 0.02 typical threshold."""
    val = _metric(sim, "icMean", "ic_mean", "IC", default=0.0)
    passed = abs(val) >= 0.02
    return CheckResult(
        check_name="ic_mean",
        passed=passed,
        actual=val,
        expected="|IC| >= 0.02",
        message=f"IC_Mean={val:.4f}" + ("" if passed else " (below 0.02)"),
    )


def _check_ic_ir(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: IC Information Ratio — IR >= 0.3 typical threshold."""
    val = _metric(sim, "icIR", "ic_ir", "IC_IR", default=0.0)
    passed = val >= 0.3
    return CheckResult(
        check_name="ic_ir",
        passed=passed,
        actual=val,
        expected=">= 0.3",
        message=f"IC_IR={val:.3f}" + ("" if passed else " (below 0.3)"),
    )


def _check_rank_ic(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "rankIC", "rank_ic", "RankIC", default=0.0)
    passed = abs(val) >= 0.02
    return CheckResult(
        check_name="rank_ic",
        passed=passed,
        actual=val,
        expected="|RankIC| >= 0.02",
        message=f"RankIC={val:.4f}",
    )


def _check_turnover_stability(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "turnoverStability", "turnover_stability", default=0.5)
    passed = val >= 0.3
    return CheckResult(
        check_name="turnover_stability",
        passed=passed,
        actual=val,
        expected=">= 0.3",
        message=f"TurnoverStability={val:.3f}",
    )


def _check_drawdown_stability(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "drawdownStability", "drawdown_stability", default=0.5)
    passed = val >= 0.3
    return CheckResult(
        check_name="drawdown_stability",
        passed=passed,
        actual=val,
        expected=">= 0.3",
        message=f"DrawdownStability={val:.3f}",
    )


def _check_coverage_minimum(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "coverage", "Coverage", default=1.0)
    passed = val >= 0.5
    return CheckResult(
        check_name="coverage_minimum",
        passed=passed,
        actual=val,
        expected=">= 0.5",
        message=f"Coverage={val:.3f}" + ("" if passed else " (below 0.5)"),
    )


def _check_expression_valid(sim: dict[str, Any]) -> CheckResult:
    errors = sim.get("errors", []) or []
    passed = len(errors) == 0
    return CheckResult(
        check_name="expression_valid",
        passed=passed,
        actual=len(errors),
        expected="0 errors",
        message="Expression valid" if passed else f"Errors: {errors}",
    )


def _check_neutralization(sim: dict[str, Any]) -> CheckResult:
    settings = sim.get("settings", {}) or {}
    neut = settings.get("neutralization", "NONE")
    passed = neut != "NONE"
    return CheckResult(
        check_name="neutralization_applied",
        passed=passed,
        actual=neut,
        expected="!= NONE",
        message=f"Neutralization={neut}",
    )


def _check_pasteurization(sim: dict[str, Any]) -> CheckResult:
    settings = sim.get("settings", {}) or {}
    past = settings.get("pasteurization", "OFF")
    passed = past == "ON"
    return CheckResult(
        check_name="pasteurization_applied",
        passed=passed,
        actual=past,
        expected="ON",
        message=f"Pasteurization={past}",
    )


def _check_delay_consistent(sim: dict[str, Any]) -> CheckResult:
    settings = sim.get("settings", {}) or {}
    delay = int(settings.get("delay", 1))
    passed = delay >= 1
    return CheckResult(
        check_name="delay_consistent",
        passed=passed,
        actual=delay,
        expected=">= 1",
        message=f"Delay={delay}",
    )


def _check_nan_handling(sim: dict[str, Any]) -> CheckResult:
    settings = sim.get("settings", {}) or {}
    nan_val = settings.get("nanHandling", "OFF")
    passed = nan_val == "ON"
    return CheckResult(
        check_name="nan_handling",
        passed=passed,
        actual=nan_val,
        expected="ON",
        message=f"NaNHandling={nan_val}",
    )


# ======================================================================
# P1-5: Type-specific checks (POWER_POOL, ATOM, PYRAMID)
# ======================================================================

def _check_powerpool_sharpe(sim: dict[str, Any]) -> CheckResult:
    """Power Pool: Sharpe >= 1.0 (lower threshold than REGULAR)."""
    val = _metric(sim, "sharpe", "Sharpe")
    passed = val >= 1.0
    return CheckResult(
        check_name="powerpool_sharpe", passed=passed, actual=val,
        expected=">= 1.0", message=f"PowerPool Sharpe={val:.3f}",
    )


def _check_powerpool_operators(sim: dict[str, Any]) -> CheckResult:
    """Power Pool: unique operators <= 8."""
    operators = sim.get("operators", []) or []
    unique = len(set(operators))
    passed = unique <= 8
    return CheckResult(
        check_name="powerpool_operators", passed=passed, actual=unique,
        expected="<= 8", message=f"PowerPool unique operators={unique}",
    )


def _check_powerpool_fields(sim: dict[str, Any]) -> CheckResult:
    """Power Pool: unique data fields <= 3 (grouping fields excluded)."""
    fields = sim.get("data_fields", sim.get("fields", [])) or []
    # Exclude grouping fields: sector, industry, subindustry, market
    grouping = {"sector", "industry", "subindustry", "market"}
    unique = len(set(f for f in fields if str(f).lower() not in grouping))
    passed = unique <= 3
    return CheckResult(
        check_name="powerpool_fields", passed=passed, actual=unique,
        expected="<= 3 (grouping excluded)", message=f"PowerPool unique fields={unique}",
    )


def _check_powerpool_self_corr(sim: dict[str, Any]) -> CheckResult:
    """Power Pool: self-correlation <= 0.5 (stricter than REGULAR's 0.7)."""
    val = abs(_metric(sim, "selfCorrelation", "self_correlation", "correlation", default=0.0))
    passed = val <= 0.5
    return CheckResult(
        check_name="powerpool_self_corr", passed=passed, actual=val,
        expected="<= 0.5", message=f"PowerPool SelfCorrelation={val:.4f}",
    )


def _check_powerpool_region_delay(sim: dict[str, Any]) -> CheckResult:
    """Power Pool: only USA, Delay-1."""
    settings = sim.get("settings", {}) or {}
    region = str(settings.get("region", "")).upper()
    delay = int(settings.get("delay", 1))
    passed = region == "USA" and delay == 1
    return CheckResult(
        check_name="powerpool_region_delay", passed=passed,
        actual=f"region={region}, delay={delay}",
        expected="region=USA, delay=1",
        message=f"PowerPool region/delay: {region}/{delay}",
    )


def _check_atom_single_dataset(sim: dict[str, Any]) -> CheckResult:
    """ATOM: all fields must come from a single dataset."""
    field_datasets = sim.get("field_datasets", sim.get("datasets", [])) or []
    unique_ds = set(str(d) for d in field_datasets if d)
    passed = len(unique_ds) <= 1
    return CheckResult(
        check_name="atom_single_dataset", passed=passed,
        actual=f"{len(unique_ds)} dataset(s): {unique_ds}",
        expected="1 dataset",
        message="ATOM single dataset" if passed else f"ATOM uses {len(unique_ds)} datasets: {unique_ds}",
    )


def _check_pyramid_count(sim: dict[str, Any]) -> CheckResult:
    """Pyramid: max 2 pyramids per user (advisory WARNING)."""
    count = int(sim.get("pyramid_count", sim.get("existing_pyramids", 0)) or 0)
    passed = count < 2
    return CheckResult(
        check_name="pyramid_count", passed=passed, actual=count,
        expected="< 2", severity="WARNING",
        message=f"Pyramid count={count}" + ("" if passed else " (max 2 reached)"),
    )


# ======================================================================
# P1-3: IS/OOS robustness check
# ======================================================================

def _check_is_oos_robustness(sim: dict[str, Any]) -> CheckResult:
    """IS/OOS robustness: SubUniverseSharpe / Sharpe >= 0.5.

    BRAIN does not natively separate IS/OOS Sharpe in standard API responses.
    We use SubUniverseSharpe/Sharpe as a proxy — a low ratio suggests the
    alpha does not generalize well across the universe (potential overfitting).

    Source: BRAIN LOW_SUB_UNIVERSE_SHARPE check formula, extended for OOS proxy.
    """
    sharpe = _metric(sim, "sharpe", "Sharpe", default=0.0)
    sub_sharpe = _metric(sim, "subUniverseSharpe", "sub_universe_sharpe", default=0.0)
    if sharpe <= 0:
        return CheckResult(
            check_name="is_oos_robustness", passed=False, actual=0.0,
            expected=">= 0.5 (SubUniverseSharpe/Sharpe)",
            message="Cannot assess IS/OOS: Sharpe <= 0",
        )
    ratio = round(sub_sharpe / max(sharpe, 0.01), 4)
    passed = ratio >= 0.5
    return CheckResult(
        check_name="is_oos_robustness", passed=passed, actual=ratio,
        expected=">= 0.5 (SubUniverseSharpe/Sharpe as OOS proxy)",
        message=f"IS/OOS ratio={ratio:.4f}" + ("" if passed else " (below 0.5 — possible overfitting)"),
    )


# ======================================================================
# P2-1: Expression complexity check
# ======================================================================

def _check_expression_complexity(sim: dict[str, Any]) -> CheckResult:
    """Expression complexity: nesting depth + operator count + expression length.

    BRAIN does not impose expression complexity limits, but complex expressions
    are harder to explain and more prone to overfitting. INFO-only advisory check.

    Source: Empirical best practice — simpler expressions generally generalize better.
    """
    expression = str(sim.get("expression", ""))
    # Nesting depth via parentheses
    depth = 0
    max_depth = 0
    for char in expression:
        if char == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif char == ")":
            depth -= 1
    # Operator count
    operators = re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression)
    op_count = len(set(operators))
    expr_len = len(expression)

    # Simple yardsticks: depth > 6, operators > 8, or length > 200 suggest complexity risk
    issues = []
    if max_depth > 6:
        issues.append(f"depth={max_depth}")
    if op_count > 8:
        issues.append(f"operators={op_count}")
    if expr_len > 200:
        issues.append(f"length={expr_len}")

    passed = len(issues) == 0
    return CheckResult(
        check_name="expression_complexity", passed=passed,
        actual=f"depth={max_depth}, ops={op_count}, len={expr_len}",
        expected="depth<=6, ops<=8, len<=200",
        message="Expression complexity OK" if passed else f"High complexity: {', '.join(issues)}",
    )
