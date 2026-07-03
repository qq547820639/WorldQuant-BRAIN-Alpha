"""Bootstrap CI, statistical helpers, and data models for ``ConvergenceTracker``.

Consolidated from the original ``convergence.py`` monolith. Holds the
``CycleRecord`` and ``ConvergenceStatus`` dataclasses, the inverse-normal-CDF
approximation / BCa adjusted-percentile / standard normal CDF helpers, and
the ``_BootstrapMixin`` carrying ``_bootstrap_ci`` (BCa bootstrap confidence
interval) and ``_spearman_trend`` (Spearman rank trend). These are mixed
into ``ConvergenceTracker`` in ``tracker``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class CycleRecord:
    """Single production cycle snapshot."""
    cycle: int
    produced: int = 0
    passed_local: int = 0
    simulated: int = 0
    passed_gate: int = 0
    submitted: int = 0
    avg_sharpe: float = 0.0
    avg_fitness: float = 0.0
    max_sharpe: float = 0.0
    avg_turnover: float = 0.0
    fusion_created: int = 0
    fusion_improvement_rate: float = 0.0
    # P1: bootstrap-compatible raw data
    raw_sharpes: list[float] = field(default_factory=list)
    raw_fitnesses: list[float] = field(default_factory=list)
    raw_turnovers: list[float] = field(default_factory=list)

@dataclass
class ConvergenceStatus:
    """Convergence tracker status report."""
    cycles_tracked: int = 0
    total_produced: int = 0
    total_submitted: int = 0
    recent_avg_sharpe: float = 0.0
    recent_max_sharpe: float = 0.0
    sharpe_trend: str = "stable"       # "improving" | "stable" | "declining"
    fitness_trend: str = "stable"
    stalled: bool = False
    stall_cycles: int = 0
    recommendation: str = ""
    cycle_history: list[dict[str, Any]] = field(default_factory=list)
    # P1: statistical fields
    sharpe_ci_low: float | None = None     # bootstrap 90% CI lower bound
    sharpe_ci_high: float | None = None    # bootstrap 90% CI upper bound
    trend_confidence: float = 0.0             # Spearman ρ or trend strength
    stall_is_significant: bool = False        # statistically significant stall


# ═══════════════════════════════════════════════════════════════════════
# Statistical helpers
# ═══════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════
# Bootstrap and trend-analysis mixin
# ═══════════════════════════════════════════════════════════════════════

class _BootstrapMixin:
    """Statistical helpers mixed into ``ConvergenceTracker``."""

    # ── P1: Bootstrap CI ────────────────────────────────────────────

    def _bootstrap_ci(
        self,
        values: list[float],
        *,
        ci_level: float = 0.90,
        use_bca: bool = True,
    ) -> tuple[float, float]:
        """Compute a confidence interval for the mean using bias-corrected
        and accelerated (BCa) bootstrap.

        P2-17 (2026-06-13): replaces the previous naive percentile
        bootstrap, which systematically narrows the CI when n is small
        (because resampling from itself cannot add information).
        BCa corrects for both the bias of the bootstrap distribution
        (when the original statistic is not centered on the parameter)
        and for the skewness of the bootstrap distribution (the
        acceleration term).

        Returns ``(0.0, 0.0)`` when ``n < 5`` since BCa jackknife
        acceleration becomes unstable with too few samples.

        Falls back to a t-distribution interval when ``n < 3`` since
        BCa needs at least a handful of distinct samples to be
        meaningful, and falls back to percentile bootstrap when
        ``use_bca=False`` (for A/B test reproducibility).

        Returns ``(ci_low, ci_high)``.
        """
        # Task 2.10: guard against empty input — otherwise the n < 3
        # branch below divides by zero (sum([]) / 0).
        if not values:
            return (0.0, 0.0)
        n = len(values)
        if n < 3:
            # n < 3: use t-distribution interval (limited data)
            mean = sum(values) / n
            variance = sum((x - mean) ** 2 for x in values) / max(n - 1, 1)
            se = (variance / n) ** 0.5 if variance > 0 else 0.01
            z = 1.645  # 90% two-sided
            return (max(0.0, mean - z * se), mean + z * se)
        # n 3-4: return (0.0, 0.0) - not enough for BCa, too much for t-dist to be reliable
        if n < 5:
            return (0.0, 0.0)

        # ── Step 1: generate B bootstrap sample means ──
        means: list[float] = []
        n_draws = min(self._bootstrap_samples, max(100, n * 10))
        for _ in range(n_draws):
            sample = [self._rng.choice(values) for _ in range(n)]
            means.append(sum(sample) / n)
        means.sort()

        if not use_bca:
            # Naive percentile bootstrap (kept for reproducibility).
            low_idx = max(0, int(len(means) * (1 - ci_level) / 2))
            high_idx = min(len(means) - 1, int(len(means) * (1 + ci_level) / 2))
            return (max(0.0, means[low_idx]), means[high_idx])

        # ── Step 2: bias correction (z0) ──
        observed_mean = sum(values) / n
        # proportion of bootstrap means strictly less than observed
        less = sum(1 for m in means if m < observed_mean)
        # avoid log(0) with a tiny floor
        p = max((less + 0.5) / (n_draws + 1.0), 1e-7)
        p = min(p, 1 - 1e-7)
        # inverse normal CDF approximation (Abramowitz & Stegun 26.2.23)
        z0 = _inv_norm_cdf(p)

        # ── Step 3: acceleration (a) via jackknife ──
        # jackknife means = leave-one-out means
        if n < 5:
            # Jackknife too unstable; fall back to percentile.
            low_idx = max(0, int(len(means) * (1 - ci_level) / 2))
            high_idx = min(len(means) - 1, int(len(means) * (1 + ci_level) / 2))
            return (max(0.0, means[low_idx]), means[high_idx])
        total = sum(values)
        jack_means = [(total - v) / (n - 1) for v in values]
        j_mean = sum(jack_means) / n
        diffs = [(j_mean - jm) for jm in jack_means]
        sum_cubes = sum(d ** 3 for d in diffs)
        sum_squares = sum(d ** 2 for d in diffs) or 1e-12
        a = sum_cubes / (6.0 * (sum_squares ** 1.5))

        # ── Step 4: BCa adjusted percentiles ──
        alpha_tail = (1.0 - ci_level) / 2.0
        alpha1 = alpha_tail
        alpha2 = 1.0 - alpha_tail
        a1 = _bca_alpha(z0, a, alpha1)
        a2 = _bca_alpha(z0, a, alpha2)
        a1 = max(0.0, min(1.0, a1))
        a2 = max(0.0, min(1.0, a2))
        low_idx = int(a1 * (len(means) - 1))
        high_idx = int(a2 * (len(means) - 1))
        return (max(0.0, means[low_idx]), means[high_idx])

    # ── P1: Spearman rank trend ─────────────────────────────────────

    def _spearman_trend(self, records: list[CycleRecord]) -> tuple[float, bool | None]:
        """Spearman rank correlation between cycle number and avg_sharpe.

        Returns (rho, trend_direction) where:
          - rho: Spearman rank correlation coefficient ∈ [-1, 1]
          - trend_direction: True=improving, False=declining, None=inconclusive
        """
        cycles = [r.cycle for r in records]
        sharpes = [r.avg_sharpe for r in records]

        n = len(cycles)
        if n < 3:
            return (0.0, None)

        # Rank cycles and sharpes
        def rank_values(vals: list[float]) -> list[float]:
            sorted_vals = sorted((v, i) for i, v in enumerate(vals))
            ranks = [0.0] * len(vals)
            i = 0
            while i < len(sorted_vals):
                j = i
                while j < len(sorted_vals) and sorted_vals[j][0] == sorted_vals[i][0]:
                    j += 1
                avg_rank = (i + j - 1) / 2.0 + 1  # 1-based
                for k in range(i, j):
                    ranks[sorted_vals[k][1]] = avg_rank
                i = j
            return ranks

        cycle_ranks = rank_values([float(c) for c in cycles])
        sharpe_ranks = rank_values(sharpes)

        # Spearman ρ = 1 - (6 * Σd²) / (n(n²-1))
        d_sq_sum = sum((cr - sr) ** 2 for cr, sr in zip(cycle_ranks, sharpe_ranks))
        denominator = n * (n * n - 1)
        rho = 1.0 - (6.0 * d_sq_sum) / denominator if denominator > 0 else 0.0

        # Direction with statistical threshold
        if abs(rho) < 0.3:
            return (rho, None)  # inconclusive
        return (rho, rho > 0)
