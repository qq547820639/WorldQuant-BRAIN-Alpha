"""``ConvergenceTracker`` class assembly.

Extracted from the original ``convergence.py`` monolith. The
``_bootstrap_ci`` and ``_spearman_trend`` statistical helpers are mixed
in via ``_BootstrapMixin`` (see ``_bootstrap_mixin``) to keep this file
under the per-submodule line budget while preserving the public class
API.
"""

from __future__ import annotations

import logging
import random
from collections import deque
from typing import Any

from brain_alpha_ops.research.convergence._bootstrap_mixin import _BootstrapMixin
from brain_alpha_ops.research.convergence._types import (
    ConvergenceStatus,
    CycleRecord,
)

# Preserve the original ``brain_alpha_ops.research.convergence`` logger
# name so downstream log filters and test caplog assertions keep working
# after the monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.convergence")


class ConvergenceTracker(_BootstrapMixin):
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
        self._rng = rng if rng is not None else random.Random()
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
