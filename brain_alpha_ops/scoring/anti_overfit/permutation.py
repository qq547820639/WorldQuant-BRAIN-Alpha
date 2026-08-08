"""Permutation-test filter for pre-screening Alpha candidates.

Circular permutation preserves the autocorrelation structure of return
series while breaking the factor–return relationship, providing a rigorous
null-distribution for significance testing.

Usage in pipeline::

    perm_filter = PermutationFilter(seed=42)
    result = perm_filter.filter(candidate_data, n_permutations=1000)
    if not result.significant:
        candidate.lifecycle_status = "REJECTED_BY_PERMUTATION_TEST"
"""

from __future__ import annotations

_NUMPY_INSTALL_HINT = (
    "NumPy is required for the permutation-test filter. Install it with: "
    "python -m pip install 'numpy>=1.26'  (or reinstall the package so the "
    "default dependency set is present)."
)


def _require_numpy():
    """Return the numpy module or raise a clear, actionable error.

    numpy is imported lazily so that importing this module never fails the
    wider test collection when numpy is absent. When the filter is actually
    used without numpy, the user gets an explicit install hint.
    """
    if _np is None:
        raise ImportError(_NUMPY_INSTALL_HINT)
    return _np


try:
    import numpy as _np
except ImportError:  # pragma: no cover - optional runtime dependency
    _np = None

import math
import random as _random
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class PermutationResult:
    """Result from a permutation-test filter run.

    Attributes:
        p_value: Empirical p-value (fraction of permuted metrics >= observed).
        significant: Whether the candidate passes the significance threshold.
        permuted_metrics: (Optional) list of metrics from each permutation.
        observed_metric: The statistic computed on un-permuted data.
        n_permutations: Number of permutations performed.
        early_stopped: Whether early-stopping terminated the loop.
    """

    p_value: float = 1.0
    significant: bool = False
    permuted_metrics: list[float] = field(default_factory=list)
    observed_metric: float = 0.0
    n_permutations: int = 0
    early_stopped: bool = False


# ---------------------------------------------------------------------------
# PermutationFilter
# ---------------------------------------------------------------------------


class PermutationFilter:
    """Circular-permutation-based significance filter for Alpha candidates.

    The filter breaks the factor–return link via circular permutation of the
    return series while preserving autocorrelation.  An empirical p-value is
    obtained by counting how many permuted metrics equal or exceed the
    observed value.  Candidates with p >= alpha are filtered out.

    Attributes:
        alpha: Significance threshold (default 0.05).
        seed: Random seed for reproducibility.
        metric: Statistic to use for comparison ("spearman", "pearson",
            "sharpe").  Defaults to "spearman".
    """

    _DEFAULT_TRIALS: int = 1000
    _EARLY_STOP_WINDOW: int = 500
    _EARLY_STOP_THRESHOLD: float = 0.10

    def __init__(
        self,
        *,
        alpha: float = 0.05,
        seed: int = 42,
        metric: str = "spearman",
    ) -> None:
        """Initialise the permutation filter.

        Args:
            alpha: Significance threshold. Candidates with p >= alpha are
                rejected.
            seed: Seed for the internal random number generator.
            metric: Which statistic to permute — "spearman", "pearson", or
                "sharpe".
        """
        self.alpha = alpha
        np_mod = _require_numpy()
        self._rng = np_mod.random.RandomState(seed)
        if metric not in ("spearman", "pearson", "sharpe"):
            raise ValueError(
                f"Unsupported metric '{metric}'; use 'spearman', 'pearson', or 'sharpe'"
            )
        self.metric = metric

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter(
        self,
        candidate: dict[str, Any],
        *,
        n_permutations: int = _DEFAULT_TRIALS,
    ) -> PermutationResult:
        """Run the permutation-test filter on a candidate.

        Extracts ``factor_values`` and ``returns`` from the candidate dict
        (supporting the same key aliases as ``AntiOverfitService``).

        Args:
            candidate: Dict with factor/return series data.  Accepted keys:
                ``factor_values``, ``factor_values_series``,
                ``returns``, ``returns_series``, ``forward_returns``.
            n_permutations: Number of permutation trials (default 1,000).

        Returns:
            ``PermutationResult`` with p-value, significance flag, etc.
        """
        np = _require_numpy()
        factor_values = self._extract_series(candidate, (
            "factor_values", "factor_values_series",
        ))
        returns = self._extract_series(candidate, (
            "returns", "returns_series", "forward_returns",
        ))

        if not factor_values or not returns:
            return PermutationResult(
                p_value=1.0,
                significant=False,
                n_permutations=0,
            )

        n = min(len(factor_values), len(returns))
        min_series = 30
        if n < min_series:
            return PermutationResult(
                p_value=1.0,
                significant=False,
                n_permutations=0,
            )

        fv = np.asarray(factor_values[:n], dtype=np.float64)
        ret = np.asarray(returns[:n], dtype=np.float64)

        observed = self._compute_metric(fv, ret)
        if not math.isfinite(observed):
            return PermutationResult(
                p_value=1.0,
                significant=False,
                observed_metric=observed,
                n_permutations=0,
            )

        permuted_metrics: list[float] = []
        exceed_count: int = 0
        early_stopped: bool = False

        for i in range(n_permutations):
            perm_ret = self.circular_permutation(ret)
            perm_metric = self._compute_metric(fv, perm_ret)
            permuted_metrics.append(perm_metric)

            if perm_metric >= observed:
                exceed_count += 1

            # Early-stop heuristic: after ``_EARLY_STOP_WINDOW`` trials,
            # if the empirical p-value has already exceeded the early-stop
            # threshold there is very little chance of dropping below
            # ``alpha``; abort to save CPU.
            if (
                not early_stopped
                and i + 1 >= self._EARLY_STOP_WINDOW
                and (i + 1 - self._EARLY_STOP_WINDOW) % 100 == 0
            ):
                p_sofar = (exceed_count + 1) / (i + 2)
                if p_sofar > self._EARLY_STOP_THRESHOLD:
                    early_stopped = True
                    # Fill remaining slots with NaN so length matches intent.
                    permuted_metrics.extend(
                        [float("nan")] * (n_permutations - i - 1)
                    )
                    break

        actual_trials = len([m for m in permuted_metrics if math.isfinite(m)])
        p_value = (exceed_count + 1) / (actual_trials + 1) if actual_trials > 0 else 1.0

        return PermutationResult(
            p_value=p_value,
            significant=p_value < self.alpha,
            permuted_metrics=permuted_metrics,
            observed_metric=observed,
            n_permutations=actual_trials,
            early_stopped=early_stopped,
        )

    # ------------------------------------------------------------------
    # Core algorithm
    # ------------------------------------------------------------------

    @staticmethod
    def circular_permutation(returns: np.ndarray) -> np.ndarray:
        """Generate a circularly-permuted copy of the returns array.

        Circular permutation preserves the autocorrelation structure by
        rotating the series rather than shuffling elements randomly.

        Args:
            returns: 1-D numpy array of return values.

        Returns:
            A new 1-D array with the same elements, circularly shifted by a
            random offset in [1, len(returns) - 1].
        """
        n = len(returns)
        if n < 2:
            return returns.copy()
        np = _require_numpy()
        offset = _random.Random().randint(1, n - 1)
        return np.concatenate([returns[offset:], returns[:offset]])

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_series(
        candidate: dict[str, Any],
        keys: tuple[str, ...],
    ) -> list[float]:
        """Extract a numeric series from ``candidate`` by priority key order."""
        for key in keys:
            val = candidate.get(key)
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                series = []
                for v in val:
                    try:
                        f = float(v)
                        if math.isfinite(f):
                            series.append(f)
                    except (TypeError, ValueError):
                        continue
                if len(series) >= 2:
                    return series
        # Fallback: try to pull from official_metrics
        metrics = candidate.get("official_metrics")
        if isinstance(metrics, dict):
            for key in keys:
                val = metrics.get(key)
                if val and isinstance(val, (list, tuple)):
                    series = []
                    for v in val:
                        try:
                            f = float(v)
                            if math.isfinite(f):
                                series.append(f)
                        except (TypeError, ValueError):
                            continue
                    if len(series) >= 2:
                        return series
        return []

    def _compute_metric(
        self,
        factor_values: np.ndarray,
        returns: np.ndarray,
    ) -> float:
        """Compute the chosen comparison statistic."""
        if self.metric == "spearman":
            return self._spearman_r(factor_values, returns)
        elif self.metric == "pearson":
            return self._pearson_r(factor_values, returns)
        elif self.metric == "sharpe":
            return self._sharpe(returns)
        return 0.0

    # -- vectorised stat helpers -----------------------------------------

    @staticmethod
    def _spearman_r(x: np.ndarray, y: np.ndarray) -> float:
        """Vectorised Spearman rank correlation using numpy."""
        n = min(len(x), len(y))
        if n < 3:
            return 0.0
        # Use argsort-based ranking (average for ties via scipy-style)
        x_rank = PermutationFilter._numpy_rank(x[:n])
        y_rank = PermutationFilter._numpy_rank(y[:n])
        return PermutationFilter._pearson_r(x_rank, y_rank)

    @staticmethod
    def _pearson_r(x: np.ndarray, y: np.ndarray) -> float:
        """Vectorised Pearson correlation using numpy."""
        np = _require_numpy()
        n = min(len(x), len(y))
        if n < 3:
            return 0.0
        xm = x[:n] - x[:n].mean()
        ym = y[:n] - y[:n].mean()
        denom = np.linalg.norm(xm) * np.linalg.norm(ym)
        if denom < 1e-15:
            return 0.0
        return float(np.dot(xm, ym) / denom)

    @staticmethod
    def _sharpe(returns: np.ndarray) -> float:
        """Annualised Sharpe ratio from daily returns."""
        np = _require_numpy()
        n = len(returns)
        if n < 5:
            return 0.0
        mean_ret = float(returns.mean())
        std_ret = float(returns.std(ddof=1))
        if std_ret < 1e-15:
            return 0.0
        return (mean_ret / std_ret) * math.sqrt(252)

    @staticmethod
    def _numpy_rank(values: np.ndarray) -> np.ndarray:
        """Compute average-rank (1-based) for a 1-D array."""
        np = _require_numpy()
        order = np.argsort(values)
        ranks = np.empty(len(values), dtype=np.float64)
        ranks[order] = np.arange(1, len(values) + 1, dtype=np.float64)
        # Handle ties: each tied group gets the mean rank
        # Use a simple iterative approach (sufficient for typical series)
        i = 0
        while i < len(values):
            j = i + 1
            while j < len(values) and values[order[j]] == values[order[i]]:
                j += 1
            if j > i + 1:
                mean_rank = (i + 1 + j) / 2.0
                for k in range(i, j):
                    ranks[order[k]] = mean_rank
            i = j
        return ranks
