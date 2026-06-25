from __future__ import annotations

from typing import Any

from .models import _IC_STABILITY_WINDOW_MIN
from .utils import _spearman_r


def estimate_half_life(
    factor_values: list[float],
    returns: list[float],
    *,
    max_lag: int = 60,
    min_half_life_days: float = 5.0,
) -> dict[str, Any]:
    """Estimate factor half-life via IC decay over increasing lags.

    Args:
        factor_values: factor exposures
        returns: forward returns
        max_lag: maximum lag to test
        min_half_life_days: minimum acceptable half-life in days

    Returns dict with half_life_days, half_life_score, decay_ics, passed.
    """
    n = min(len(factor_values), len(returns))
    if n < max_lag + _IC_STABILITY_WINDOW_MIN:
        return {
            "half_life_days": 0.0, "half_life_score": 0.0,
            "decay_ics": [], "passed": False,
            "warning": f"insufficient samples ({n} < {max_lag + _IC_STABILITY_WINDOW_MIN})",
        }

    decay_ics: list[float] = []
    for lag in range(0, min(max_lag, n - _IC_STABILITY_WINDOW_MIN) + 1):
        if lag == 0:
            ic = _spearman_r(factor_values[:n], returns[:n])
        else:
            ic = _spearman_r(factor_values[:n - lag], returns[lag:])
        decay_ics.append(ic)

    initial_ic = abs(decay_ics[0]) if decay_ics else 0.0
    half_life = 0.0
    if initial_ic > 1e-8:
        target_ic = initial_ic / 2.0
        for lag, ic in enumerate(decay_ics):
            if abs(ic) <= target_ic:
                half_life = float(lag)
                break
        else:
            half_life = float(max_lag)

    half_life_score = min(100.0, (half_life / max(min_half_life_days, 1.0)) * 50.0)
    passed = bool(half_life >= min_half_life_days)

    return {
        "half_life_days": half_life,
        "half_life_score": half_life_score,
        "decay_ics": decay_ics,
        "passed": passed,
    }
