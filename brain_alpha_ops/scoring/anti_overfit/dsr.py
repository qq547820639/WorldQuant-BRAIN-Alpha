"""Deflated Sharpe Ratio (DSR) computation.

DSR simultaneously corrects for selection bias and non-normality, adjusting
Sharpe-ratio significance using extreme-value theory.

Reference
---------
Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe Ratio:
Correcting for Selection Bias, Backtest Overfitting, and Non-Normality."
Journal of Portfolio Management, 40(5), 94–107.

Key thresholds
--------------
- DSR > 0.95  — strong evidence (best-in-class signal)
- DSR < 0.50  — indistinguishable from random
- DSR > 0.70  — moderate evidence
- DSR > 0.30  — weak evidence (hypothesis-driven filtering floor)
- DSR < 0.30  — reject for hypothesis-driven strategies
- DSR < 0.50  — reject for data-driven strategies (higher bar)

When ``trial_count == 1`` the DSR degenerates to the Probabilistic Sharpe
Ratio (PSR).
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# erfinv approximation (S. Winitzki, 2008)
# ---------------------------------------------------------------------------
# a = 8 / (3 * pi) * (pi - 3) / (4 - pi)
#   ≈ 0.1400122886866665
# Maximum relative error < 0.0012 across the domain (-1, 1).
# ---------------------------------------------------------------------------
_ERFINV_A = 8.0 / (3.0 * math.pi) * (math.pi - 3.0) / (4.0 - math.pi)
_ERFINV_COEF = 2.0 / (math.pi * _ERFINV_A)


def _erfinv(x: float) -> float:
    """Approximate the inverse error function for ``x`` in (-1, 1).

    Uses the rational approximation derived by Sergei Winitzki (2008).
    Boundary points (±1) are handled by the caller.
    """
    if x <= -1.0:
        return -math.inf
    if x >= 1.0:
        return math.inf
    if abs(x) < 1e-15:
        return 0.0

    sign = 1.0 if x >= 0.0 else -1.0
    # Work with positive x
    x_abs = abs(x)
    ln_one_minus_x2 = math.log(1.0 - x_abs * x_abs)

    a = _ERFINV_COEF + ln_one_minus_x2 / 2.0
    inner = math.sqrt(a * a - ln_one_minus_x2 / _ERFINV_A) - a
    return sign * math.sqrt(max(0.0, inner))


# ---------------------------------------------------------------------------
# DSR computation
# ---------------------------------------------------------------------------


def compute_dsr(
    sharpe: float,
    t_stat: float,
    trial_count: int,
) -> float:
    """Compute the Deflated Sharpe Ratio (DSR).

    DSR is the probability (under the standard-normal cdf) that the observed
    Sharpe ratio is statistically significant after accounting for selection
    bias induced by ``trial_count`` independent trials.

    Args:
        sharpe: Annualised Sharpe ratio of the strategy.
        t_stat: t-statistic of the Sharpe estimate (= sharpe / SE).
        trial_count: Number of independent trials (candidates / hypotheses)
            considered alongside this one.  Must be >= 1.

    Returns:
        DSR value in [0, 1].

        - DSR > 0.95:  strong evidence of genuine signal.
        - DSR < 0.50:  indistinguishable from random.
        - For ``trial_count == 1`` the result equals PSR.

    Raises:
        ValueError: If ``trial_count`` < 1 or ``t_stat`` is non-positive
            (computationally degenerate).
    """
    if trial_count < 1:
        raise ValueError(f"trial_count must be >= 1, got {trial_count}")
    if t_stat <= 0.0 or sharpe <= 0.0:
        return 0.0

    # ------------------------------------------------------------------
    # Expected maximum Sharpe under the null (extreme-value theory):
    #
    #   E[max SR | N trials] ≈ sqrt(2) * erfinv(1 - 1/N)
    #
    # When N = 1: erfinv(0) = 0  →  E_max = 0  →  PSR (base case).
    # ------------------------------------------------------------------
    if trial_count == 1:
        e_max = 0.0
    else:
        e_max = math.sqrt(2.0) * _erfinv(1.0 - 1.0 / trial_count)
        # _erfinv may return inf when input is too close to 1.
        if math.isinf(e_max):
            e_max = math.sqrt(2.0 * math.log(trial_count))  # asymptotic form

    # Standard error of the Sharpe estimate
    se = abs(sharpe) / t_stat

    # DSR = Φ((SR - E_max) / SE)
    z_score = (sharpe - e_max) / max(se, 1e-15)
    dsr_value = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))

    return float(max(0.0, min(1.0, dsr_value)))
