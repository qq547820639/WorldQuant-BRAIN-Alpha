from __future__ import annotations

from typing import Any

from .models import _IC_STABILITY_WINDOW_MIN, _PLACEBO_TRIALS
from .utils import _spearman_r


def compute_placebo_test(
    factor_values: list[float],
    returns: list[float],
    *,
    trials: int = _PLACEBO_TRIALS,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Placebo test: compare real IC against random-permuted baselines.

    Returns p-value (fraction of permuted ICs >= real IC) and placebo_score.
    """
    n = min(len(factor_values), len(returns))
    if n < _IC_STABILITY_WINDOW_MIN:
        return {
            "p_value": 1.0, "placebo_score": 0.0, "passed": False,
            "warning": f"insufficient samples ({n} < {_IC_STABILITY_WINDOW_MIN})",
        }

    import random as _random
    rng = _random.Random(42)

    real_ic = abs(_spearman_r(factor_values[:n], returns[:n]))

    placebo_ics: list[float] = []
    ret_list = list(returns[:n])
    for _ in range(trials):
        rng.shuffle(ret_list)
        placebo_ics.append(abs(_spearman_r(factor_values[:n], ret_list)))

    exceed_count = sum(1 for pic in placebo_ics if pic >= real_ic)
    p_value = (exceed_count + 1) / (trials + 1)

    placebo_score = max(0.0, min(100.0, (1.0 - p_value / alpha) * 100.0))
    passed = bool(p_value < alpha)

    return {
        "p_value": p_value,
        "placebo_score": placebo_score,
        "passed": passed,
    }
