"""BRAIN official Alpha Checks — advanced & type-specific check functions.

IC checks, stability, coverage, structure, data compliance, type-specific
checks (POWER_POOL / ATOM / PYRAMID), IS/OOS robustness, and expression
complexity.
"""
from __future__ import annotations

import re
from typing import Any

from brain_alpha_ops.research.alpha_checks._checks_basic import _metric
from brain_alpha_ops.research.alpha_checks._types import CheckResult


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
