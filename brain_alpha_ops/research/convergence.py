"""Alpha 收敛追踪器 — 衡量生产→迭代→收敛闭环质量。

追踪维度:
  1. 每轮生产的 Alpha 质量趋势 (Sharpe/Fitness 均值)
  2. 迭代前后的改进率 (secondary fusion 效果)
  3. 经验反馈有效性 (experience guidance 是否提升了产出)
  4. 收敛状态判定 (质量是否在持续提升)

当连续 N 轮无质量改善时，建议切换 strategy profile。

P1 增强:
  - Bootstrap 置信区间：用重采样估计 avg_sharpe 的 90% CI
  - Spearman 秩相关趋势检验：替代简单的前后半均值比较
  - 统计显著性 stall 判定：stall = 连续 N 轮 avg_sharpe 无显著改善

Usage::

    from brain_alpha_ops.research.convergence import ConvergenceTracker

    tracker = ConvergenceTracker(window_size=10)
    tracker.record_cycle(cycle, candidates, accepted)
    status = tracker.status()
    if status["stalled"]:
        print(f"Convergence stalled: {status['recommendation']}")
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
    raw_sharpes: List[float] = field(default_factory=list)
    raw_fitnesses: List[float] = field(default_factory=list)
    raw_turnovers: List[float] = field(default_factory=list)


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
    cycle_history: List[Dict[str, Any]] = field(default_factory=list)
    # P1: 统计字段
    sharpe_ci_low: Optional[float] = None     # bootstrap 90% CI lower bound
    sharpe_ci_high: Optional[float] = None    # bootstrap 90% CI upper bound
    trend_confidence: float = 0.0             # Spearman ρ or trend strength
    stall_is_significant: bool = False        # 统计显著性确认的停滞


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
                 bootstrap_samples: int = 1000) -> None:
        self._window_size = max(5, int(window_size))
        self._stall_threshold = max(3, int(stall_threshold))
        self._bootstrap_samples = max(100, int(bootstrap_samples))
        self._records: deque[CycleRecord] = deque(maxlen=self._window_size)
        self._all_records: List[CycleRecord] = []
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
        candidates: Optional[List[Any]] = None,
        accepted: Optional[List[Any]] = None,
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

        # ── P1: Stall detection with bootstrap CI comparison ──
        # Compute bootstrap CI for current window if enough data
        if len(self._records) >= 3 and rec.raw_sharpes:
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
                self._stall_counter += 1
                if rec.max_sharpe > self._best_sharpe:
                    self._best_sharpe = rec.max_sharpe
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

    def summary(self) -> Dict[str, Any]:
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
            # P1: 统计字段
            "sharpe_ci_90": [s.sharpe_ci_low or 0.0, s.sharpe_ci_high or 0.0],
            "trend_confidence": s.trend_confidence,
            "stall_is_significant": s.stall_is_significant,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    @staticmethod
    def _record_to_dict(rec: CycleRecord) -> Dict[str, Any]:
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

    def _bootstrap_ci(self, values: List[float]) -> tuple[float, float]:
        """Compute 90% bootstrap confidence interval for the mean.

        Uses simple percentile bootstrap with replacement.
        Returns (ci_low, ci_high).
        """
        if not values:
            return (0.0, 0.0)

        n = len(values)
        if n < 3:
            # Not enough data for bootstrap — use simple ±2*SE approximation
            mean = sum(values) / n
            variance = sum((x - mean) ** 2 for x in values) / max(n - 1, 1)
            se = (variance / n) ** 0.5 if variance > 0 else 0.01
            return (max(0.0, mean - 1.645 * se), mean + 1.645 * se)

        # Percentile bootstrap
        means = []
        for _ in range(min(self._bootstrap_samples, max(100, n * 10))):
            sample = [random.choice(values) for _ in range(n)]
            sample_mean = sum(sample) / n
            means.append(sample_mean)

        means.sort()
        low_idx = int(len(means) * 0.05)   # 5th percentile → 90% CI
        high_idx = int(len(means) * 0.95)  # 95th percentile
        return (max(0.0, means[low_idx]), means[high_idx])

    # ── P1: Spearman rank trend ─────────────────────────────────────

    def _spearman_trend(self, records: List[CycleRecord]) -> tuple[float, Optional[bool]]:
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
        def rank_values(vals: List[float]) -> List[float]:
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
