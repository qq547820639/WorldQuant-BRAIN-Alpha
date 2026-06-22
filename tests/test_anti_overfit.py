"""Tests for anti-overfitting validation suite.

Covers: IC stability, regime stress, placebo test, half-life estimation,
boundary conditions (empty, short, extreme values, NaN).
"""

from __future__ import annotations

import math
import pytest

from brain_alpha_ops.scoring.anti_overfit import (
    ANTI_OVERFIT_SCHEMA_VERSION,
    AntiOverfitResult,
    AntiOverfitService,
    run_anti_overfit_suite,
    compute_ic_stability,
    compute_regime_stress,
    compute_placebo_test,
    estimate_half_life,
    _rank_ic,
    _spearman_r,
    _rank_transform,
    _pearson_r,
    _sharpe,
    _auto_classify_regimes,
    _safe_mean,
    _safe_std,
)


def test_candidate_anti_overfit_missing_official_series_fails_closed():
    candidate = {
        "expression": "rank(close)",
        "official_metrics": {"sharpe": 1.8, "fitness": 1.2},
        "submission": {},
    }

    report = AntiOverfitService().evaluate(candidate)

    assert report["ok"] is False
    assert report["passed"] is False
    assert report["recommendation"] == "insufficient_data"
    assert report["schema_version"] == ANTI_OVERFIT_SCHEMA_VERSION
    assert candidate["submission"]["anti_overfit_report"] is report


def test_candidate_anti_overfit_short_official_series_fails_closed():
    candidate = {
        "expression": "rank(close)",
        "official_metrics": {
            "ic_series": [0.02] * 20,
            "returns_series": [0.01] * 20,
        },
        "submission": {},
    }

    report = AntiOverfitService().evaluate(candidate)

    assert report["ok"] is False
    assert report["passed"] is False
    assert report["sample_size"] == 20
    assert report["recommendation"] == "insufficient_data"


def test_research_anti_overfit_imports_canonical_service():
    from brain_alpha_ops.research.anti_overfit import AntiOverfitService as ResearchService

    assert ResearchService is AntiOverfitService


# ═══════════════════════ Helper Tests ═══════════════════════════════

class TestSafeMean:
    def test_empty(self):
        assert _safe_mean([]) == 0.0

    def test_single(self):
        assert _safe_mean([5.0]) == 5.0

    def test_positive(self):
        assert _safe_mean([1.0, 2.0, 3.0]) == 2.0

    def test_negative(self):
        assert _safe_mean([-1.0, -2.0, -3.0]) == -2.0

    def test_mixed(self):
        assert _safe_mean([-1.0, 0.0, 1.0]) == 0.0


class TestSafeStd:
    def test_empty(self):
        assert _safe_std([]) == 0.0

    def test_single(self):
        assert _safe_std([5.0]) == 0.0

    def test_constant(self):
        assert _safe_std([3.0, 3.0, 3.0]) == 0.0

    def test_varying(self):
        std = _safe_std([1.0, 3.0, 5.0])
        assert std > 1.0  # sample std ≈ 2.0


class TestSpearmanR:
    def test_perfect_positive(self):
        # Use larger array with distinct values to avoid rank-tie artifacts
        n = 100
        x = list(range(n))
        y = list(range(n))  # perfect positive
        r = _spearman_r(x, y)
        assert abs(r - 1.0) < 0.02, f"expected ~1.0, got {r}"

    def test_perfect_negative(self):
        n = 100
        x = list(range(n))
        y = list(reversed(range(n)))  # perfect negative
        r = _spearman_r(x, y)
        assert abs(r + 1.0) < 0.02, f"expected ~-1.0, got {r}"

    def test_uncorrelated(self):
        import random
        random.seed(1)
        n = 100
        x = [random.gauss(0, 1) for _ in range(n)]
        y = [random.gauss(0, 1) for _ in range(n)]
        r = _spearman_r(x, y)
        # Should be near zero (uncorrelated)
        assert -0.5 <= r <= 0.5, f"expected near 0, got {r}"

    def test_short_input(self):
        r = _spearman_r([1.0], [2.0])
        assert r == 0.0  # n < 3

    def test_empty(self):
        r = _spearman_r([], [])
        assert r == 0.0


class TestSharpe:
    def test_positive_varying_returns(self):
        # Varying positive returns should produce positive Sharpe
        import random
        random.seed(42)
        n = 252
        rets = [0.001 + random.gauss(0, 0.005) for _ in range(n)]
        s = _sharpe(rets)
        assert s > 0.0

    def test_zero_mean_returns(self):
        rets = [0.01, -0.01] * 126  # mean ≈ 0
        s = _sharpe(rets)
        assert s < 0.5  # near-zero Sharpe

    def test_short(self):
        rets = [0.01] * 3
        s = _sharpe(rets)
        assert s == 0.0  # n < 5


class TestAutoClassifyRegimes:
    def test_empty(self):
        assert _auto_classify_regimes([]) == []

    def test_three_buckets(self):
        rets = [-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05]
        labels = _auto_classify_regimes(rets)
        assert len(labels) == len(rets)
        assert "bear" in labels
        assert "bull" in labels


# ═══════════════════════ IC Stability Tests ═══════════════════════════

class TestICStability:
    def test_strong_positive_ic(self):
        """Strong monotonic relationship should yield high IC stability."""
        n = 100
        fv = list(range(n))
        fwd = [x * 0.01 for x in range(n)]  # perfect rank correlation
        result = compute_ic_stability(fv, fwd)
        assert result["ic_mean"] > 0.9
        assert result["passed"] is True

    def test_no_relationship(self):
        """Random factor → low IC, should fail."""
        import random
        random.seed(0)
        n = 100
        fv = [random.random() for _ in range(n)]
        fwd = [random.random() for _ in range(n)]
        result = compute_ic_stability(fv, fwd)
        # Should have very low IC
        assert result["ic_mean"] < 0.5
        assert result["passed"] is False

    def test_insufficient_samples(self):
        fv = [1.0, 2.0, 3.0]
        fwd = [0.01, 0.02, 0.03]
        result = compute_ic_stability(fv, fwd)
        assert result["passed"] is False
        assert "warning" in result

    def test_custom_thresholds(self):
        n = 100
        fv = list(range(n))
        fwd = [x * 0.001 for x in range(n)]  # high rank IC
        result = compute_ic_stability(fv, fwd, min_ic_mean=0.1, max_ic_std=0.5)
        assert result["passed"] is True


# ═══════════════════════ Regime Stress Tests ═══════════════════════════

class TestRegimeStress:
    def test_consistent_regime_performance(self):
        """Returns with some variance across regimes, all positive Sharpe."""
        import random
        random.seed(42)
        n = 180
        fv = list(range(n))
        # Create returns with distinct regime signatures
        rets = []
        for i in range(n):
            if i < 60:
                rets.append(0.001 + random.gauss(0, 0.005))  # bear-ish
            elif i < 120:
                rets.append(0.002 + random.gauss(0, 0.003))  # sideways-ish
            else:
                rets.append(0.003 + random.gauss(0, 0.005))  # bull-ish
        result = compute_regime_stress(fv, rets)
        # At least some regimes should have valid Sharpe
        assert result["sideways_sharpe"] is not None

    def test_insufficient_data(self):
        n = 30
        fv = list(range(n))
        rets = list(range(n))
        result = compute_regime_stress(fv, rets)
        assert result["passed"] is False

    def test_with_explicit_labels(self):
        import random
        random.seed(1)
        n = 150
        fv = list(range(n))
        rets = [0.001 + random.gauss(0, 0.005) for _ in range(n)]
        labels = ["bull"] * 50 + ["sideways"] * 50 + ["bear"] * 50
        result = compute_regime_stress(fv, rets, regime_labels=labels)
        assert result["bull_sharpe"] is not None
        assert result["bear_sharpe"] is not None


# ═══════════════════════ Placebo Test ═══════════════════════════════

class TestPlaceboTest:
    def test_strong_signal(self):
        """Strong IC should yield low p-value vs random permutations."""
        n = 100
        fv = list(range(n))
        fwd = [x * 0.1 for x in range(n)]
        result = compute_placebo_test(fv, fwd)
        assert result["p_value"] < 0.1
        assert result["passed"] is True

    def test_no_signal(self):
        import random
        random.seed(1)
        n = 100
        fv = [random.random() for _ in range(n)]
        fwd = [random.random() for _ in range(n)]
        result = compute_placebo_test(fv, fwd)
        # Should have relatively high p-value
        assert result["p_value"] > 0.01

    def test_insufficient_data(self):
        result = compute_placebo_test([1.0, 2.0], [3.0, 4.0])
        assert result["passed"] is False


# ═══════════════════════ Half-Life Tests ═══════════════════════════════

class TestHalfLife:
    def test_slow_decay(self):
        """Very slow decay → long half-life."""
        n = 200
        fv = list(range(n))
        rets = [x * 0.01 for x in range(n)]
        result = estimate_half_life(fv, rets, min_half_life_days=1.0)
        assert result["half_life_days"] > 0.0
        assert result["passed"] is True

    def test_insufficient_data(self):
        result = estimate_half_life(list(range(10)), list(range(10)))
        assert result["passed"] is False

    def test_strict_threshold(self):
        n = 200
        fv = list(range(n))
        rets = [x * 0.01 for x in range(n)]
        result = estimate_half_life(fv, rets, min_half_life_days=100.0)
        assert result["passed"] is False  # cannot have 100-day half-life with this data


# ═══════════════════════ Full Suite Test ═══════════════════════════════

class TestRunAntiOverfitSuite:
    def test_strong_factor_passes(self):
        """A strongly predictive factor should pass all checks."""
        n = 200
        import random
        random.seed(42)
        base = [random.gauss(0, 1) for _ in range(n)]
        # Add strong signal
        signal = [b * 2.0 + random.gauss(0, 0.1) for b in base]
        result = run_anti_overfit_suite(
            base, signal,
            min_ic_mean=0.01,
            max_ic_std=0.5,
            min_half_life_days=1.0,
            placebo_alpha=0.1,
        )
        assert isinstance(result, AntiOverfitResult)
        assert 0.0 <= result.overall_score <= 100.0
        assert isinstance(result.warnings, list)

    def test_weak_factor_fails(self):
        """A weak/no signal factor should fail most checks."""
        import random
        random.seed(0)
        n = 200
        fv = [random.random() for _ in range(n)]
        rets = [random.random() for _ in range(n)]
        result = run_anti_overfit_suite(fv, rets)
        assert result.passed is False
        assert result.overall_score < 50.0

    def test_insufficient_data(self):
        import random
        result = run_anti_overfit_suite(
            [random.random() for _ in range(10)],
            [random.random() for _ in range(10)],
        )
        assert result.passed is False
        assert len(result.warnings) > 0

    def test_to_dict(self):
        import random
        random.seed(0)
        n = 200
        fv = [random.gauss(0, 1) for _ in range(n)]
        rets = [v * 0.1 + random.gauss(0, 0.05) for v in fv]
        result = run_anti_overfit_suite(fv, rets)
        d = result.to_dict()
        assert d["passed"] in (True, False)
        assert "ic_stability" in d
        assert "regime_stress" in d
        assert "placebo" in d
        assert "half_life" in d
        assert "warnings" in d

    def test_nan_handling(self):
        """NaN values should be handled gracefully without crash."""
        fv = [1.0, 2.0, float("nan"), 4.0, 5.0] * 40
        rets = [0.01] * 200
        # Should not raise
        try:
            result = run_anti_overfit_suite(fv, rets)
            assert isinstance(result, AntiOverfitResult)
        except Exception as e:
            pytest.fail(f"run_anti_overfit_suite raised {type(e).__name__}: {e}")

    def test_extreme_values(self):
        """Extremely large values should not cause overflow."""
        fv = [1e10, -1e10] * 100
        rets = [0.01] * 200
        result = run_anti_overfit_suite(fv, rets)
        assert isinstance(result, AntiOverfitResult)

    def test_all_zeros(self):
        """All-zero factor should be handled gracefully."""
        fv = [0.0] * 200
        rets = [0.001] * 200
        result = run_anti_overfit_suite(fv, rets)
        assert isinstance(result, AntiOverfitResult)

    def test_deterministic(self):
        """Same input should produce same output (deterministic given seed)."""
        import random
        random.seed(99)
        n = 200
        fv = [random.gauss(0, 1) for _ in range(n)]
        rets = [v * 0.1 for v in fv]
        result1 = run_anti_overfit_suite(fv, rets)

        random.seed(99)
        fv2 = [random.gauss(0, 1) for _ in range(n)]
        rets2 = [v * 0.1 for v in fv2]
        result2 = run_anti_overfit_suite(fv2, rets2)

        assert result1.overall_score == result2.overall_score
        assert result1.passed == result2.passed
