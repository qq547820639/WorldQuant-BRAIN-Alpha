from __future__ import annotations

from typing import Any

from .models import _REGIME_MIN_SAMPLES
from .utils import _auto_classify_regimes, _sharpe


def compute_regime_stress(
    factor_values: list[float],
    returns: list[float],
    *,
    regime_labels: list[str] | None = None,
    min_samples_per_regime: int = _REGIME_MIN_SAMPLES,
) -> dict[str, Any]:
    """Test factor performance across different market regimes (bull/bear/sideways).

    If regime_labels are not provided, auto-classify based on return percentiles:
      - bear: bottom 33%
      - sideways: middle 34%
      - bull: top 33%

    Returns dict with bull_sharpe, bear_sharpe, sideways_sharpe, regime_stability_score, passed.
    """
    n = min(len(factor_values), len(returns))
    if n < min_samples_per_regime * 3:
        return {
            "bull_sharpe": None, "bear_sharpe": None, "sideways_sharpe": None,
            "regime_stability_score": 0.0, "passed": False,
            "warning": f"insufficient samples ({n} < {min_samples_per_regime * 3})",
        }

    if regime_labels is None:
        regime_labels = _auto_classify_regimes(returns[:n])

    bull_ret: list[float] = []
    bear_ret: list[float] = []
    sideways_ret: list[float] = []
    for i, label in enumerate(regime_labels[:n]):
        if label == "bull":
            bull_ret.append(returns[i])
        elif label == "bear":
            bear_ret.append(returns[i])
        else:
            sideways_ret.append(returns[i])

    bull_sharpe = _sharpe(bull_ret) if len(bull_ret) >= min_samples_per_regime else None
    bear_sharpe = _sharpe(bear_ret) if len(bear_ret) >= min_samples_per_regime else None
    sideways_sharpe = _sharpe(sideways_ret) if len(sideways_ret) >= min_samples_per_regime else None

    sharpes = [s for s in (bull_sharpe, bear_sharpe, sideways_sharpe) if s is not None]
    if len(sharpes) >= 2 and max(sharpes) - min(sharpes) < 1e-9:
        regime_stability_score = 100.0
    elif sharpes:
        dispersion = max(0.001, max(sharpes) - min(sharpes))
        regime_stability_score = max(0.0, min(100.0, 100.0 / (1.0 + dispersion)))
    else:
        regime_stability_score = 0.0

    passed = bool(
        sharpes
        and all(s >= 0 for s in sharpes)
        and regime_stability_score >= 40.0
    )

    return {
        "bull_sharpe": bull_sharpe,
        "bear_sharpe": bear_sharpe,
        "sideways_sharpe": sideways_sharpe,
        "regime_stability_score": regime_stability_score,
        "passed": passed,
    }
