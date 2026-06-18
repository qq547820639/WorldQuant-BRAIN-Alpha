"""Alpha quality diagnostics engine for analyzing official backtest failures.

All thresholds come from the BRAIN official Alpha Check standard (Delay-1):
  LOW_SHARPE, LOW_FITNESS, LOW_TURNOVER, HIGH_TURNOVER,
  CONCENTRATED_WEIGHT, SELF_CORRELATION, LOW_SUB_UNIVERSE_SHARPE

Usage::

    from brain_alpha_ops.research.diagnostics import diagnose
    from brain_alpha_ops.config import QualityThresholds

    diag = diagnose(candidate, QualityThresholds())
    if diag["primary_failure"]:
        print(f"Primary failure: {diag['primary_failure']}")
        for mut in diag["suggested_mutations"]:
            print(f"  -> {mut}")
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brain_alpha_ops.models import Candidate

def _num(value: Any) -> float:
    """Safely convert to float."""
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0

# P0-4 fix (2026-06-13): the four ``_ratio()`` definitions across
# research/{scoring,experience,safety,diagnostics}.py are now unified in
# ``research._ratio``. The local wrapper preserves the historical function
# name and signature.
from brain_alpha_ops.research._ratio import normalize_brain_ratio  # noqa: F401


def _ratio(value: Any) -> float:
    return normalize_brain_ratio(value, bounded=False)

def diagnose(
    candidate: "Candidate",
    thresholds: Any,  # QualityThresholds
) -> dict[str, Any]:
    """Analyze an Alpha's official backtest result and return failure reasons.

    Returns:
        {
            "alpha_id": str,
            "lifecycle_status": str,
            "primary_failure": str | None,
            "failed_dimensions": [...],
            "suggested_mutations": [
                {"dimension": str, "mutation_mode": str, "suggestions": [...]},
            ],
            "summary": str,
        }
    """
    metrics = candidate.official_metrics or {}
    gate = candidate.gate or {}

    diagnosis: dict[str, Any] = {
        "alpha_id": candidate.alpha_id,
        "lifecycle_status": candidate.lifecycle_status,
        "primary_failure": None,
        "failed_dimensions": [],
        "suggested_mutations": [],
        "summary": "",
    }

    # Extract metrics (aligned with BRAIN official API normalize_metrics).
    sharpe = _num(metrics.get("sharpe"))
    fitness = _num(metrics.get("fitness"))
    turnover = _ratio(metrics.get("turnover"))
    correlation = abs(_ratio(metrics.get("correlation")))
    concentration = _ratio(metrics.get("weight_concentration"))
    margin = _num(metrics.get("margin", 0.0))
    sub_universe_sharpe = _num(metrics.get("sub_universe_sharpe", 0.0))

    # Thresholds from QualityThresholds (BRAIN official standards).
    min_sharpe = getattr(thresholds, "min_sharpe", 1.25)
    min_fitness = getattr(thresholds, "min_fitness", 1.0)
    min_turnover = getattr(thresholds, "min_turnover", 0.01)
    platform_max_turnover = getattr(thresholds, "platform_max_turnover", 0.70)
    target_max_turnover = getattr(thresholds, "target_max_turnover", 0.30)
    max_correlation = getattr(thresholds, "max_self_correlation", 0.70)
    max_concentration = getattr(thresholds, "max_weight_concentration", 0.10)
    min_margin_bps = getattr(thresholds, "min_margin_bps", 4.0)
    sub_sharpe_ratio = getattr(thresholds, "sub_universe_sharpe_min_ratio", 0.75)

    # Diagnose each dimension.

    # Sharpe (BRAIN: LOW_SHARPE if < 1.25)
    if sharpe < min_sharpe:
        diagnosis["failed_dimensions"].append("sharpe")
        diagnosis["suggested_mutations"].append({
            "dimension": "sharpe",
            "mutation_mode": "structure_change",
            "suggestions": [
                "winsorize/zscore wrap to reduce outlier impact",
                "try inverse (rank(-expr)) for reversal alpha",
                "add volume filter (adv20/volume) for liquidity adjustment",
            ],
        })

    # Fitness (BRAIN: LOW_FITNESS if < 1.0)
    if fitness < min_fitness:
        diagnosis["failed_dimensions"].append("fitness")
        diagnosis["suggested_mutations"].append({
            "dimension": "fitness",
            "mutation_mode": "structure_change",
            "suggestions": [
                "add neutralization or truncation",
                "use longer window for stability",
                "simplify expression — reduce operator nesting",
            ],
        })

    # Turnover HIGH — platform hard gate (BRAIN: HIGH_TURNOVER if > 70%).
    if turnover > platform_max_turnover:
        diagnosis["failed_dimensions"].append("turnover_platform")
        diagnosis["suggested_mutations"].append({
            "dimension": "turnover",
            "mutation_mode": "longer_window",
            "suggestions": [
                "use longer windows (60→120→252) for slower turnover",
                "replace rank() with ts_rank() with larger window",
                "add truncation to reduce extreme weights",
            ],
        })
    # Turnover QUALITY — advisor target (turnover > 30% can still be optimized).
    elif turnover > target_max_turnover:
        diagnosis["failed_dimensions"].append("turnover_quality")
        diagnosis["suggested_mutations"].append({
            "dimension": "turnover",
            "mutation_mode": "longer_window",
            "suggestions": [
                f"Turnover={turnover:.1%} > {target_max_turnover:.0%} target — optimize instead of dropping",
                "increase decay to improve signal persistence",
                "add smoothing (ts_mean/ts_decay_linear) to reduce noisy triggers",
                "extend the lookback window to reduce turnover",
                "use trade_when to avoid unnecessary rebalancing",
                "reduce short-horizon signal weight, especially small-window ts_delta/ts_rank",
            ],
        })

    # Turnover LOW (BRAIN: LOW_TURNOVER if < 1%).
    if turnover < min_turnover:
        diagnosis["failed_dimensions"].append("turnover_low")
        diagnosis["suggested_mutations"].append({
            "dimension": "turnover",
            "mutation_mode": "field_swap",
            "suggestions": [
                "use shorter windows for faster signal response",
                "switch from ts_mean to ts_delta for directional change",
                "use higher-frequency fields (daily over monthly)",
            ],
        })

    # Correlation (BRAIN: SELF_CORRELATION if >= 0.70).
    if correlation >= max_correlation:
        diagnosis["failed_dimensions"].append("correlation")
        diagnosis["suggested_mutations"].append({
            "dimension": "correlation",
            "mutation_mode": "field_swap",
            "suggestions": [
                "use different data fields from another dataset",
                "change operator chain — swap ts_mean for ts_std or ts_corr",
                "add group_neutralize for within-sector independence",
            ],
        })

    # Concentration (BRAIN: CONCENTRATED_WEIGHT if > 10%).
    if concentration > max_concentration:
        diagnosis["failed_dimensions"].append("concentration")
        diagnosis["suggested_mutations"].append({
            "dimension": "concentration",
            "mutation_mode": "structure_change",
            "suggestions": [
                "add truncation to cap extreme weights",
                "use rank() instead of raw values for uniform distribution",
                "add pasteurization ON for outlier handling",
            ],
        })

    # Margin (BRAIN advisor target).
    if margin < min_margin_bps:
        diagnosis["failed_dimensions"].append("margin")
        diagnosis["suggested_mutations"].append({
            "dimension": "margin",
            "mutation_mode": "structure_change",
            "suggestions": [
                "increase signal strength via winsorize + rank chain",
                "reduce complexity — fewer nested operators",
                "try multiplicative composite (rank(A)*rank(B))",
            ],
        })

    # Sub-universe Sharpe (BRAIN: LOW_SUB_UNIVERSE_SHARPE).
    sub_threshold = sub_sharpe_ratio * max(sharpe, 0.01)
    if sub_universe_sharpe < sub_threshold:
        diagnosis["failed_dimensions"].append("sub_universe_sharpe")
        diagnosis["suggested_mutations"].append({
            "dimension": "sub_universe_sharpe",
            "mutation_mode": "structure_change",
            "suggestions": [
                "switch neutralization: SUBINDUSTRY→SECTOR→MARKET",
                "use group_rank for cross-sectional consistency",
                "add universe filter for higher-quality stocks",
            ],
        })

    # Determine the primary failure.
    if diagnosis["failed_dimensions"]:
        diagnosis["primary_failure"] = diagnosis["failed_dimensions"][0]
        diagnosis["summary"] = (
            f"Alpha {candidate.alpha_id}: {len(diagnosis['failed_dimensions'])} dimension(s) failed — "
            f"primary={diagnosis['primary_failure']}. "
            f"Suggested {len(diagnosis['suggested_mutations'])} mutation path(s)."
        )
    else:
        diagnosis["summary"] = f"Alpha {candidate.alpha_id}: all dimensions pass thresholds."
        # Check gate-level failures.
        gate_failures = gate.get("failed_reasons", [])
        if gate_failures:
            diagnosis["failed_dimensions"].append("gate")
            diagnosis["primary_failure"] = "gate"
            diagnosis["summary"] += f" Gate failures: {'; '.join(str(f) for f in gate_failures[:3])}"

    return diagnosis

def get_mutation_mode(diagnosis: dict[str, Any], fallback: str = "default") -> str:
    """Extract the most suitable mutation mode from a diagnosis result.

    Returns one of: "default", "field_swap", "structure_change", "longer_window"
    """
    mutations = diagnosis.get("suggested_mutations", [])
    if not mutations:
        return fallback
    # Return the mode of the first (highest-priority) mutation.
    return mutations[0].get("mutation_mode", fallback)
