"""Statistical helper functions for the ``convergence`` subpackage.

Extracted from the original ``convergence.py`` monolith. Holds the
inverse-normal-CDF approximation, the BCa adjusted-percentile helper, and
the standard normal CDF used by the bootstrap confidence interval logic.
"""

from __future__ import annotations

import math


# ── P2-17: BCa bootstrap helpers (2026-06-13) ─────────────────────────
def _inv_norm_cdf(p: float) -> float:
    """Inverse of the standard normal CDF (Abramowitz & Stegun 26.2.23).

    Accurate to ~1e-7 for p in (0, 1).
    """
    if p <= 0.0:
        return -4.0
    if p >= 1.0:
        return 4.0
    # rational approximation for lower tail
    t = math.sqrt(-2.0 * math.log(min(p, 1.0 - p)))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    z = t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
    return z if p >= 0.5 else -z

def _bca_alpha(z0: float, a: float, alpha: float) -> float:
    """Compute a single BCa adjusted percentile.

    The formula is::
        alpha' = Phi(z0 + (z0 + z_alpha) / (1 - a * (z0 + z_alpha)))
    where ``Phi`` is the standard normal CDF and ``z_alpha`` is its inverse.
    """
    z_alpha = _inv_norm_cdf(alpha)
    denom = 1.0 - a * (z0 + z_alpha)
    if abs(denom) < 1e-9:
        denom = 1e-9 if denom >= 0 else -1e-9
    return _normal_cdf(z0 + (z0 + z_alpha) / denom)

def _normal_cdf(z: float) -> float:
    """Standard normal CDF via the Abramowitz & Stegun 7.1.26 approximation."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
