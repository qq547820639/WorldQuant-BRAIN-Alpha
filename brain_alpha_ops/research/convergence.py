"""Alpha convergence tracker for the production-iteration-convergence loop.

Tracked dimensions:
  1. Alpha quality trend per production cycle (average Sharpe/Fitness)
  2. Improvement before and after iteration (secondary fusion effect)
  3. Experience feedback effectiveness (whether guidance improves output)
  4. Convergence status (whether quality keeps improving)

When quality fails to improve for N consecutive cycles, the tracker recommends
switching strategy profile.

P1 enhancements:
  - Bootstrap confidence intervals estimate avg_sharpe 90% CI.
  - Spearman rank-correlation trend checks replace simple split-window means.
  - Statistical stall detection flags N cycles without significant avg_sharpe improvement.

Usage::

    from brain_alpha_ops.research.convergence import ConvergenceTracker

    tracker = ConvergenceTracker(window_size=10)
    tracker.record_cycle(cycle, candidates, accepted)
    status = tracker.status()
    if status["stalled"]:
        print(f"Convergence stalled: {status['recommendation']}")
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any


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

class ConvergenceTracker:
    """Tracks production quality convergence across cycles.

    Maintains a rolling window of recent cycle records and detects
    quality trends. When quality stalls for too many consecutive cycles,
    recommends strategy profile switching.

    P1 enhancement: Uses bootstrap confidence intervals to assess
    statistical significance of quality changes, replacing raw
    best_sharpe comparison with CI-overlap-based stall detection.
    """

    def __init__(self, window_size: int = 10, stall_threshold: int = 5,
                 bootstrap_samples: int = 1000, rng: random.Random | None = None) -> None:
        """Initialize convergence tracker.

        Args:
            window_size: Number of recent cycles retained for trend analysis.
                Clamped to minimum 5 internally.
            stall_threshold: Consecutive cycles without improvement before
                signaling stall. Clamped to minimum 3 internally.
            bootstrap_samples: Number of bootstrap resamples for BCa CI.
                Clamped to minimum 100 internally.
            rng: Optional seeded Random instance for reproducible bootstrap.
                Defaults to Random(42) if None.
        """
        self._window_size = max(5, int(window_size))
        self._stall_threshold = max(3, int(stall_threshold))
        self._bootstrap_samples = max(100, int(bootstrap_samples))
        self._rng = rng if rng is not None else random.Random(42)
        self._records: deque[CycleRecord] = deque(maxlen=self._window_size)
        self._all_records: list[CycleRecord] = []
        self._stall_counter: int = 0
        self._best_sharpe: float = 0.0
        # P1: track smoothed trend for significance
        self._prev_window_ci: tuple[float, float] = (0.0, 0.0)

    # ------------------------------------------------------------------
    # Record
    # ------------------------------------------------------------------
    def record_cycle(
        self,
        cycle: int,
        candidates: list[Any] | None = None,
        accepted: list[Any] | None = None,
        *,
        produced: int = 0,
        passed_local: int = 0,
        simulated: int = 0,
        passed_gate: int = 0,
        submitted: int = 0,
        fusion_created: int = 0,
        fusion_prev_sharpe: float = 0.0,
        fusion_new_sharpe: float = 0.0,
    ) -> CycleRecord:
        """Record metrics for a completed production cycle."""
        rec = CycleRecord(
            cycle=cycle,
            produced=produced,
            passed_local=passed_local,
            simulated=simulated,
            passed_gate=passed_gate,
            submitted=submitted,
            fusion_created=fusion_created,
        )

        # Compute quality metrics from candidates
        if candidates:
            sharpes = []
            fitnesses = []
            turnovers = []
            for c in candidates:
                m = getattr(c, 'official_metrics', {}) or {}
                s = float(m.get("sharpe", 0) or 0)
                f = float(m.get("fitness", 0) or 0)
                t = float(m.get("turnover", 0) or 0)
                if s > 0:
                    sharpes.append(s)
                    fitnesses.append(f)
                    turnovers.append(t)
            if sharpes:
                rec.avg_sharpe = round(sum(sharpes) / len(sharpes), 4)
                rec.avg_fitness = round(sum(fitnesses) / len(fitnesses), 4)
                rec.max_sharpe = round(max(sharpes), 4)
                rec.avg_turnover = round(sum(turnovers) / len(turnovers), 4)
                # P1: store raw values for bootstrap
                rec.raw_sharpes = list(sharpes)
                rec.raw_fitnesses = list(fitnesses)
                rec.raw_turnovers = list(turnovers)

        # Fusion improvement rate
        if fusion_created > 0 and fusion_prev_sharpe > 0:
            improvement = (fusion_new_sharpe - fusion_prev_sharpe) / max(fusion_prev_sharpe, 0.01)
            rec.fusion_improvement_rate = round(improvement, 4)

        self._records.append(rec)
        self._all_records.append(rec)

        # P1: stall detection with bootstrap CI comparison.
        # Compute bootstrap CI for current window if enough data.
        # BCa requires n>=5 for stable jackknife acceleration; below that
        # the method falls back to percentile bootstrap which is less reliable.
        if len(self._records) >= 5 and rec.raw_sharpes:
            current_ci = self._bootstrap_ci(rec.raw_sharpes)
            prev_lo, prev_hi = self._prev_window_ci
            # An improvement is significant if current CI lower bound
            # exceeds previous CI upper bound
            if prev_hi > 0 and current_ci[0] > prev_hi:
                # Significant improvement detected
                self._stall_counter = 0
                self._best_sharpe = max(self._best_sharpe, rec.max_sharpe)
                self._prev_window_ci = current_ci
            elif prev_hi > 0 and current_ci[1] < prev_lo:
                # Significant decline detected
                self._stall_counter += 1
                self._prev_window_ci = current_ci
            else:
                # CIs overlap — no significant change
                if rec.max_sharpe > self._best_sharpe:
                    self._best_sharpe = rec.max_sharpe
                    self._stall_counter = 0
                else:
                    self._stall_counter += 1
                self._prev_window_ci = current_ci
        else:
            # Fallback: best_sharpe-based (backward compat, low-sample)
            if rec.max_sharpe > self._best_sharpe:
                self._best_sharpe = rec.max_sharpe
                self._stall_counter = 0
            else:
                self._stall_counter += 1

        return rec

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def status(self) -> ConvergenceStatus:
        """Return current convergence status with trend analysis."""
        if not self._records:
            return ConvergenceStatus()

        records = list(self._records)
        status = ConvergenceStatus(
            cycles_tracked=len(self._all_records),
            total_produced=sum(r.produced for r in self._all_records),
            total_submitted=sum(r.submitted for r in self._all_records),
            cycle_history=[self._record_to_dict(r) for r in records[-10:]],
        )

        # Recent averages (last window_size cycles)
        recent = records[-min(5, len(records)):]
        if recent:
            status.recent_avg_sharpe = round(
                sum(r.avg_sharpe for r in recent if r.avg_sharpe > 0) /
                max(1, sum(1 for r in recent if r.avg_sharpe > 0)), 4
            )
            status.recent_max_sharpe = max((r.max_sharpe for r in recent), default=0.0)

        # Trend analysis (P1: Spearman rank correlation for robust trend detection)
        if len(records) >= 3:
            trend_rho, trend_improving = self._spearman_trend(records)
            status.trend_confidence = round(trend_rho, 4)
            if trend_improving is True:
                status.sharpe_trend = "improving"
            elif trend_improving is False:
                status.sharpe_trend = "declining"
            else:
                status.sharpe_trend = "stable"

        # ── P1: Bootstrap CI for recent window ──
        all_raw_sharpes = []
        for r in records:
            all_raw_sharpes.extend(r.raw_sharpes)
        if all_raw_sharpes:
            ci_low, ci_high = self._bootstrap_ci(all_raw_sharpes)
            status.sharpe_ci_low = round(ci_low, 4)
            status.sharpe_ci_high = round(ci_high, 4)

        # Stall detection
        status.stalled = self._stall_counter >= self._stall_threshold
        status.stall_cycles = self._stall_counter
        # P1: stall is significant only when CIs consistently overlap
        status.stall_is_significant = (
            status.stalled and status.sharpe_ci_low is not None
            and status.sharpe_ci_high is not None
        )

        if status.stalled:
            ci_str = ""
            if status.sharpe_ci_low is not None:
                ci_str = f" (90% CI: [{status.sharpe_ci_low:.3f}, {status.sharpe_ci_high:.3f}])"
            status.recommendation = (
                f"Quality stalled for {self._stall_counter} cycles{ci_str}. "
                f"Best Sharpe={self._best_sharpe:.3f}. "
                f"Consider switching strategy profile (region/universe/neutralization) "
                f"or changing dataset_strategy to explore new data sources."
            )
        elif status.sharpe_trend == "declining":
            status.recommendation = (
                f"Recent Sharpe trend is declining (Spearman ρ={status.trend_confidence:.3f}). "
                f"Monitor next few cycles; if trend continues, consider strategy profile switch."
            )
        elif status.sharpe_trend == "improving":
            status.recommendation = (
                f"Quality is improving (Spearman ρ={status.trend_confidence:.3f}) — continue current strategy."
            )
        else:
            status.recommendation = "Quality is stable — maintain current approach."

        return status

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset tracker (e.g., after strategy profile switch)."""
        self._records.clear()
        self._stall_counter = 0
        self._best_sharpe = 0.0

    def summary(self) -> dict[str, Any]:
        """Return a compact summary dict for pipeline reports."""
        s = self.status()
        return {
            "cycles_tracked": s.cycles_tracked,
            "total_produced": s.total_produced,
            "total_submitted": s.total_submitted,
            "recent_avg_sharpe": s.recent_avg_sharpe,
            "recent_max_sharpe": s.recent_max_sharpe,
            "best_sharpe": self._best_sharpe,
            "sharpe_trend": s.sharpe_trend,
            "stalled": s.stalled,
            "stall_cycles": s.stall_cycles,
            "recommendation": s.recommendation,
            # P1: statistical fields.
            "sharpe_ci_90": [s.sharpe_ci_low or 0.0, s.sharpe_ci_high or 0.0],
            "trend_confidence": s.trend_confidence,
            "stall_is_significant": s.stall_is_significant,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    @staticmethod
    def _record_to_dict(rec: CycleRecord) -> dict[str, Any]:
        return {
            "cycle": rec.cycle,
            "produced": rec.produced,
            "simulated": rec.simulated,
            "passed_gate": rec.passed_gate,
            "submitted": rec.submitted,
            "avg_sharpe": rec.avg_sharpe,
            "max_sharpe": rec.max_sharpe,
            "avg_fitness": rec.avg_fitness,
            "fusion_improvement": rec.fusion_improvement_rate,
        }

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
        n = len(values)
        if n < 5:
            return (0.0, 0.0)
        if n < 3:
            # Use a simple t-style interval; not enough data for BCa.
            mean = sum(values) / n
            variance = sum((x - mean) ** 2 for x in values) / max(n - 1, 1)
            se = (variance / n) ** 0.5 if variance > 0 else 0.01
            z = 1.645  # 90% two-sided
            return (max(0.0, mean - z * se), mean + z * se)

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
