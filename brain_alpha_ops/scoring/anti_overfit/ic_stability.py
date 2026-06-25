from __future__ import annotations

from typing import Any

from .models import _IC_STABILITY_WINDOW_MIN
from .utils import _rank_ic, _safe_mean, _safe_std


def compute_ic_stability(
    factor_values: list[float],
    forward_returns: list[float],
    *,
    group_ids: list[int] | None = None,
    min_ic_mean: float = 0.02,
    max_ic_std: float = 0.08,
) -> dict[str, Any]:
    """Compute IC (rank correlation) stability metrics.

    Args:
        factor_values: factor exposures
        forward_returns: forward returns aligned with factor values
        group_ids: optional group labels for cross-sectional IC per group
        min_ic_mean: minimum acceptable mean IC
        max_ic_std: maximum acceptable IC standard deviation

    Returns dict with ic_mean, ic_std, ic_stability_score, monthly_means, passed.
    """
    n = min(len(factor_values), len(forward_returns))
    if n < _IC_STABILITY_WINDOW_MIN:
        return {
            "ic_mean": 0.0, "ic_std": 0.0, "ic_stability_score": 0.0,
            "monthly_means": [], "passed": False,
            "warning": f"insufficient samples ({n} < {_IC_STABILITY_WINDOW_MIN})",
        }

    ics = _rank_ic(factor_values[:n], forward_returns[:n])
    ic_mean_val = _safe_mean(ics)
    ic_std_val = _safe_std(ics, ic_mean_val)

    mean_score = min(100.0, max(0.0, (ic_mean_val / max(min_ic_mean, 0.001)) * 50.0))
    stability_score = min(50.0, max(0.0, (1.0 - ic_std_val / max(max_ic_std, 0.001)) * 50.0))
    ic_stability_score = mean_score + stability_score

    monthly_means: list[float] = []
    chunk = max(1, n // max(1, n // 21))
    for i in range(0, len(ics), chunk):
        chunk_ics = ics[i:i + chunk]
        if chunk_ics:
            monthly_means.append(_safe_mean(chunk_ics))

    passed = bool(ic_mean_val >= min_ic_mean and ic_std_val <= max_ic_std)

    return {
        "ic_mean": ic_mean_val,
        "ic_std": ic_std_val,
        "ic_stability_score": ic_stability_score,
        "monthly_means": monthly_means,
        "passed": passed,
    }
