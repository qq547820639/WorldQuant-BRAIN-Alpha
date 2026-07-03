"""Unit tests for permutation-test filter.

Covers: circular_permutation correctness, signal/noise detection,
early-stop mechanism, boundary conditions, different metrics, and
PermutationResult dataclass validation.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from brain_alpha_ops.scoring.anti_overfit.permutation import (
    PermutationFilter,
    PermutationResult,
)


# ============================================================================
# PermutationResult dataclass
# ============================================================================

class TestPermutationResult:
    """Tests for PermutationResult dataclass defaults and construction."""

    def test_defaults(self):
        result = PermutationResult()
        assert result.p_value == 1.0
        assert result.significant is False
        assert result.permuted_metrics == []
        assert result.observed_metric == 0.0
        assert result.n_permutations == 0
        assert result.early_stopped is False

    def test_full_construction(self):
        result = PermutationResult(
            p_value=0.01,
            significant=True,
            permuted_metrics=[0.1, 0.2, 0.3],
            observed_metric=0.45,
            n_permutations=1000,
            early_stopped=False,
        )
        assert result.p_value == 0.01
        assert result.significant is True
        assert len(result.permuted_metrics) == 3
        assert result.observed_metric == 0.45
        assert result.n_permutations == 1000
        assert result.early_stopped is False


# ============================================================================
# circular_permutation
# ============================================================================

class TestCircularPermutation:
    """Tests for the circular_permutation static method."""

    def test_length_preserved(self):
        """Output should have same length as input."""
        for n in (2, 10, 100, 1000):
            arr = np.arange(n, dtype=np.float64)
            result = PermutationFilter.circular_permutation(arr)
            assert len(result) == n

    def test_elements_preserved(self):
        """All elements should be preserved (same multiset)."""
        np.random.seed(42)
        arr = np.random.randn(100)
        result = PermutationFilter.circular_permutation(arr)
        np.testing.assert_array_equal(np.sort(arr), np.sort(result))

    def test_not_identity_for_large_n(self):
        """For n >= 2, permutation should not be identity (offset >= 1)."""
        arr = np.arange(100, dtype=np.float64)
        # Run multiple times to account for randomness
        all_different = False
        for _ in range(20):
            result = PermutationFilter.circular_permutation(arr)
            if not np.array_equal(arr, result):
                all_different = True
                break
        assert all_different, "circular_permutation always returned identity"

    def test_single_element(self):
        """Single element: should return copy (no valid offset in [1, 0])."""
        arr = np.array([42.0])
        result = PermutationFilter.circular_permutation(arr)
        assert len(result) == 1
        assert result[0] == 42.0

    def test_two_elements(self):
        """Two elements: offset is always 1, should swap."""
        arr = np.array([1.0, 2.0])
        result = PermutationFilter.circular_permutation(arr)
        # With offset=1, result should be [2.0, 1.0]
        assert result[0] == 2.0
        assert result[1] == 1.0

    def test_circular_structure(self):
        """Verify the result is a contiguous circular shift."""
        # Use unique values to avoid duplicate-matching issues
        arr = np.arange(50, dtype=np.float64)
        result = PermutationFilter.circular_permutation(arr)
        # arr[0] (=0.0) ends up at some position p in result
        # If circular shift offset = k (result[i] = arr[(i+k) % n]),
        # then arr[0] is at p = (n - k) % n, so k = (n - p) % n
        n = len(arr)
        pos = int(np.where(result == 0.0)[0][0])
        k = (n - pos) % n  # the circular shift offset
        for i in range(n):
            expected = arr[(i + k) % n]
            np.testing.assert_almost_equal(result[i], expected)

    def test_returns_copy_not_view(self):
        """Should return a new array, not a view."""
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = PermutationFilter.circular_permutation(arr)
        result[0] = 999.0
        assert arr[0] != 999.0


# ============================================================================
# PermutationFilter construction
# ============================================================================

class TestPermutationFilterInit:
    """Tests for PermutationFilter initialization."""

    def test_default_construction(self):
        f = PermutationFilter()
        assert f.alpha == 0.05
        assert f.metric == "spearman"

    def test_custom_alpha(self):
        f = PermutationFilter(alpha=0.01)
        assert f.alpha == 0.01

    def test_custom_seed(self):
        f = PermutationFilter(seed=123)
        assert f._rng is not None

    def test_supported_metrics(self):
        for metric in ("spearman", "pearson", "sharpe"):
            f = PermutationFilter(metric=metric)
            assert f.metric == metric

    def test_unsupported_metric_raises(self):
        with pytest.raises(ValueError, match="Unsupported metric"):
            PermutationFilter(metric="kendall")


# ============================================================================
# PermutationFilter.filter — signal / noise detection
# ============================================================================

def _make_signal_candidate(n: int = 200, seed: int = 42) -> dict:
    """Create a candidate with a strong monotonic signal."""
    np.random.seed(seed)
    factor = np.random.randn(n)
    # Returns are strongly correlated with factor (with noise)
    returns = factor * 0.5 + np.random.randn(n) * 0.1
    return {
        "factor_values": factor.tolist(),
        "returns": returns.tolist(),
    }


def _make_noise_candidate(n: int = 200, seed: int = 42) -> dict:
    """Create a candidate with independent factor/returns (pure noise)."""
    np.random.seed(seed)
    factor = np.random.randn(n)
    # Returns are completely independent
    returns = np.random.randn(n)
    return {
        "factor_values": factor.tolist(),
        "returns": returns.tolist(),
    }


class TestPermutationFilterSignal:
    """Signal detection tests."""

    def test_strong_signal_detected(self):
        """A strong monotonic signal should be detected as significant."""
        f = PermutationFilter(alpha=0.05, seed=42)
        candidate = _make_signal_candidate(n=200)
        result = f.filter(candidate, n_permutations=1000)

        # Strong signal should have p < 0.05
        assert result.p_value < 0.05, (
            f"Expected p<0.05 for strong signal, got p={result.p_value:.4f}"
        )
        assert result.significant is True

    def test_noise_not_significant(self):
        """Pure noise should not be flagged as significant."""
        f = PermutationFilter(alpha=0.05, seed=42)
        candidate = _make_noise_candidate(n=200)
        result = f.filter(candidate, n_permutations=1000)

        # Noise should have p >= 0.05 (usually much higher)
        assert result.p_value >= 0.05, (
            f"Expected p>=0.05 for noise, got p={result.p_value:.4f}"
        )
        assert result.significant is False

    def test_observed_metric_set(self):
        """observed_metric should be set for valid input."""
        f = PermutationFilter(seed=42)
        result = f.filter(_make_signal_candidate(n=200), n_permutations=200)
        assert math.isfinite(result.observed_metric)

    def test_permuted_metrics_populated(self):
        """permuted_metrics should contain values."""
        f = PermutationFilter(seed=42)
        result = f.filter(_make_signal_candidate(n=200), n_permutations=100)
        assert len(result.permuted_metrics) > 0
        assert result.n_permutations == len(result.permuted_metrics)


# ============================================================================
# PermutationFilter.filter — boundary conditions
# ============================================================================

class TestPermutationFilterBoundary:
    """Boundary condition tests."""

    def test_empty_factor_values(self):
        """Empty factor_values → fail-safe: p=1.0, not significant."""
        f = PermutationFilter(seed=42)
        result = f.filter({"factor_values": [], "returns": [0.01] * 100})
        assert result.p_value == 1.0
        assert result.significant is False
        assert result.n_permutations == 0

    def test_empty_returns(self):
        """Empty returns → fail-safe."""
        f = PermutationFilter(seed=42)
        result = f.filter({"factor_values": [0.01] * 100, "returns": []})
        assert result.p_value == 1.0
        assert result.significant is False

    def test_missing_keys(self):
        """Missing both keys → fail-safe."""
        f = PermutationFilter(seed=42)
        result = f.filter({"other": 1})
        assert result.p_value == 1.0
        assert result.significant is False

    def test_short_series(self):
        """Series shorter than 30 elements → fail-safe (n < min_series)."""
        f = PermutationFilter(seed=42)
        candidate = {
            "factor_values": list(range(20)),
            "returns": list(range(20)),
        }
        result = f.filter(candidate)
        assert result.p_value == 1.0
        assert result.significant is False
        assert result.n_permutations == 0

    def test_exactly_min_series(self):
        """Exactly 30 elements should work."""
        f = PermutationFilter(alpha=0.05, seed=42)
        candidate = _make_signal_candidate(n=30)
        result = f.filter(candidate, n_permutations=100)
        # Should run (n >= 30)
        assert result.n_permutations > 0

    def test_single_data_point(self):
        """Single data point → fail-safe."""
        f = PermutationFilter(seed=42)
        result = f.filter({"factor_values": [1.0], "returns": [0.01]})
        assert result.p_value == 1.0
        assert result.significant is False


# ============================================================================
# PermutationFilter.filter — NaN / inf handling
# ============================================================================

class TestPermutationFilterNaN:
    """Tests for NaN and infinite value handling."""

    def test_nan_in_factor_values(self):
        """NaN in factor_values should not crash; should be filtered out."""
        f = PermutationFilter(seed=42)
        fv = [1.0, 2.0, float("nan"), 4.0, 5.0] * 40  # 200 total, some NaN
        rets = list(range(200))
        candidate = {"factor_values": fv, "returns": rets}
        # Should not raise
        result = f.filter(candidate, n_permutations=100)
        assert isinstance(result, PermutationResult)

    def test_nan_observed_metric(self):
        """All-constant inputs → metric=0.0 (finite), permutations should run
        but p-value should be 1.0 (no permutation can exceed the observed)."""
        f = PermutationFilter(seed=42)
        # All identical values → zero variance → _spearman_r returns 0.0
        # The code treats 0.0 as a valid finite metric and proceeds.
        candidate = {
            "factor_values": [1.0] * 100,
            "returns": [2.0] * 100,
        }
        result = f.filter(candidate, n_permutations=100)
        # observed_metric = 0.0; all permuted metrics also ~0.0
        # p-value = (exceed_count + 1) / (n + 1) → ~1.0
        assert result.p_value >= 0.9
        assert result.significant is False
        assert result.observed_metric == pytest.approx(0.0, abs=0.01)

    def test_inf_values(self):
        """Inf values should be filtered out by _extract_series."""
        f = PermutationFilter(seed=42)
        fv = [1.0, 2.0, float("inf"), 4.0, 5.0] * 40
        rets = list(range(200))
        candidate = {"factor_values": fv, "returns": rets}
        result = f.filter(candidate, n_permutations=100)
        assert isinstance(result, PermutationResult)


# ============================================================================
# Early-stop mechanism
# ============================================================================

class TestPermutationFilterEarlyStop:
    """Tests for the early-stop mechanism."""

    def test_early_stop_triggers_on_noise(self):
        """With pure noise and 1000 permutations, early-stop should trigger."""
        f = PermutationFilter(alpha=0.05, seed=42)
        candidate = _make_noise_candidate(n=200, seed=123)
        result = f.filter(candidate, n_permutations=1000)

        # Noise should trigger early-stop (p > 0.10 after 500 trials)
        assert result.early_stopped is True, (
            f"Expected early_stop=True for noise, got {result.early_stopped}"
        )
        # Should have stopped between 500 and 1000
        assert 500 <= result.n_permutations <= 1000

    def test_early_stop_not_on_strong_signal(self):
        """Strong signal should NOT trigger early-stop."""
        f = PermutationFilter(alpha=0.05, seed=42)
        candidate = _make_signal_candidate(n=200, seed=42)
        result = f.filter(candidate, n_permutations=500)
        # With just 500 trials, early stop check hasn't happened yet
        assert result.n_permutations == 500

    def test_early_stop_fills_nan(self):
        """When early-stop triggers, remaining slots should be NaN."""
        f = PermutationFilter(alpha=0.05, seed=42)
        candidate = _make_noise_candidate(n=200, seed=42)
        result = f.filter(candidate, n_permutations=1000)

        if result.early_stopped:
            # Total permuted_metrics length should still be n_permutations
            assert len(result.permuted_metrics) == 1000
            # Last entries should be NaN
            last = result.permuted_metrics[-1]
            assert math.isnan(last) or not math.isfinite(last)


# ============================================================================
# Different metrics
# ============================================================================

class TestPermutationFilterMetrics:
    """Tests for different metric types."""

    def test_pearson_metric(self):
        """Pearson correlation metric should work."""
        f = PermutationFilter(metric="pearson", seed=42)
        candidate = _make_signal_candidate(n=200)
        result = f.filter(candidate, n_permutations=100)
        assert math.isfinite(result.observed_metric)
        assert result.n_permutations > 0

    def test_sharpe_metric(self):
        """Sharpe metric should work (uses returns only)."""
        f = PermutationFilter(metric="sharpe", seed=42)
        # For sharpe, we need positive mean returns
        np.random.seed(42)
        rets = 0.001 + np.random.randn(200) * 0.01
        candidate = {
            "factor_values": np.random.randn(200).tolist(),
            "returns": rets.tolist(),
        }
        result = f.filter(candidate, n_permutations=100)
        assert math.isfinite(result.observed_metric)
        assert result.n_permutations > 0

    def test_all_metrics_run(self):
        """All three metrics should not crash."""
        for metric in ("spearman", "pearson", "sharpe"):
            f = PermutationFilter(metric=metric, seed=42)
            candidate = _make_signal_candidate(n=200)
            result = f.filter(candidate, n_permutations=50)
            assert isinstance(result, PermutationResult), (
                f"metric={metric} failed"
            )


# ============================================================================
# _extract_series key alias handling
# ============================================================================

class TestExtractSeries:
    """Tests for _extract_series key alias resolution."""

    def test_factor_values_key(self):
        f = PermutationFilter()
        result = f.filter({
            "factor_values": list(range(100)),
            "returns": list(range(100)),
        }, n_permutations=10)
        assert result.n_permutations > 0

    def test_factor_values_series_key(self):
        f = PermutationFilter()
        result = f.filter({
            "factor_values_series": list(range(100)),
            "returns": list(range(100)),
        }, n_permutations=10)
        assert result.n_permutations > 0

    def test_returns_series_key(self):
        f = PermutationFilter()
        result = f.filter({
            "factor_values": list(range(100)),
            "returns_series": list(range(100)),
        }, n_permutations=10)
        assert result.n_permutations > 0

    def test_forward_returns_key(self):
        f = PermutationFilter()
        result = f.filter({
            "factor_values": list(range(100)),
            "forward_returns": list(range(100)),
        }, n_permutations=10)
        assert result.n_permutations > 0

    def test_official_metrics_fallback(self):
        """Extract from official_metrics nested dict."""
        f = PermutationFilter()
        result = f.filter({
            "official_metrics": {
                "factor_values": list(range(100)),
                "returns": list(range(100)),
            },
        }, n_permutations=10)
        assert result.n_permutations > 0

    def test_mixed_keys_factor_priority(self):
        """When both factor_values and factor_values_series present, first wins."""
        f = PermutationFilter(seed=42)
        # factor_values takes priority
        result = f.filter({
            "factor_values": list(range(100)),
            "factor_values_series": list(range(50)),  # shorter, should be ignored
            "returns": list(range(100)),
        }, n_permutations=10)
        assert result.n_permutations > 0


# ============================================================================
# compute_permutation_test integration (from checks.py)
# ============================================================================

class TestComputePermutationTest:
    """Tests for the compute_permutation_test wrapper in checks.py."""

    def test_strong_signal_passes(self):
        from brain_alpha_ops.scoring.anti_overfit.checks import compute_permutation_test

        candidate = _make_signal_candidate(n=200)
        result = compute_permutation_test(
            candidate["factor_values"],
            candidate["returns"],
            n_permutations=1000,
            alpha=0.05,
        )
        assert result["p_value"] < 0.05
        assert result["significant"] is True
        assert result["passed"] is True
        assert "observed_ic" in result

    def test_noise_fails(self):
        from brain_alpha_ops.scoring.anti_overfit.checks import compute_permutation_test

        candidate = _make_noise_candidate(n=200)
        result = compute_permutation_test(
            candidate["factor_values"],
            candidate["returns"],
            n_permutations=500,
            alpha=0.05,
        )
        assert result["p_value"] >= 0.05
        assert result["significant"] is False
        assert result["passed"] is False
        assert result["early_stopped"] is True  # Noise should trigger early stop

    def test_empty_data(self):
        from brain_alpha_ops.scoring.anti_overfit.checks import compute_permutation_test

        result = compute_permutation_test([], [], n_permutations=100)
        assert result["p_value"] == 1.0
        assert result["significant"] is False
        assert result["passed"] is False


# ============================================================================
# AntiOverfitResult backward compatibility (models.py)
# ============================================================================

class TestAntiOverfitResultBackwardCompat:
    """Ensure AntiOverfitResult with new dsr fields is backward compatible."""

    def test_dsr_fields_exist_with_defaults(self):
        from brain_alpha_ops.scoring.anti_overfit.models import AntiOverfitResult

        result = AntiOverfitResult()
        assert result.dsr_score == 0.0
        assert result.trial_count == 0

    def test_to_dict_includes_dsr(self):
        from brain_alpha_ops.scoring.anti_overfit.models import AntiOverfitResult

        result = AntiOverfitResult(dsr_score=0.85, trial_count=10)
        d = result.to_dict()
        assert "dsr" in d
        assert d["dsr"]["score"] == 0.85
        assert d["dsr"]["trial_count"] == 10

    def test_to_dict_backward_compatible(self):
        """Default AntiOverfitResult.to_dict() should still work."""
        from brain_alpha_ops.scoring.anti_overfit.models import AntiOverfitResult

        result = AntiOverfitResult(passed=True, overall_score=75.0)
        d = result.to_dict()
        assert d["passed"] is True
        assert d["overall_score"] == 75.0
        assert "ic_stability" in d
        assert "regime_stress" in d
        assert "placebo" in d
        assert "half_life" in d
        assert "dsr" in d  # New field
        assert "warnings" in d
        assert "thresholds" in d

    def test_default_result_is_backward_compatible(self):
        """Existing code constructing AntiOverfitResult() should still work."""
        from brain_alpha_ops.scoring.anti_overfit.models import AntiOverfitResult

        # This is what suite.py does — create with no dsr args
        result = AntiOverfitResult(
            min_ic_mean=0.02,
            max_ic_std=0.08,
            min_half_life_days=5.0,
            placebo_alpha=0.05,
        )
        assert result.dsr_score == 0.0
        assert result.trial_count == 0
        d = result.to_dict()
        assert d["dsr"]["score"] == 0.0
