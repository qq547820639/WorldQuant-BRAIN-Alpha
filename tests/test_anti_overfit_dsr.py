"""Unit tests for Deflated Sharpe Ratio (DSR) computation.

Covers: PSR degenerate case (N=1), EVT correction (N>1), boundary conditions,
mathematical correctness against known reference values, and error handling.
"""

from __future__ import annotations

import math

import pytest

from brain_alpha_ops.scoring.anti_overfit.dsr import compute_dsr, _erfinv


# ============================================================================
# _erfinv helper tests
# ============================================================================

class TestErfinv:
    """Tests for the internal erfinv approximation."""

    def test_erfinv_zero(self):
        """erfinv(0) should be 0."""
        assert _erfinv(0.0) == 0.0

    def test_erfinv_near_zero(self):
        """Very small values should be 0 (under threshold)."""
        assert _erfinv(1e-16) == 0.0
        assert _erfinv(-1e-16) == 0.0

    def test_erfinv_boundary_positive(self):
        """erfinv(1.0) → +inf."""
        assert math.isinf(_erfinv(1.0))
        assert _erfinv(1.0) > 0

    def test_erfinv_boundary_negative(self):
        """erfinv(-1.0) → -inf."""
        assert math.isinf(_erfinv(-1.0))
        assert _erfinv(-1.0) < 0

    def test_erfinv_beyond_boundary(self):
        """Values beyond ±1 also return ±inf."""
        assert math.isinf(_erfinv(1.5))
        assert math.isinf(_erfinv(-1.5))

    def test_erfinv_symmetry(self):
        """erfinv(-x) should equal -erfinv(x)."""
        for x in (0.1, 0.3, 0.5, 0.7, 0.9, 0.99):
            assert _erfinv(-x) == pytest.approx(-_erfinv(x), rel=1e-4)

    def test_erfinv_monotonic(self):
        """erfinv should be monotonically increasing."""
        vals = [_erfinv(x) for x in (0.1, 0.3, 0.5, 0.7, 0.9)]
        for i in range(len(vals) - 1):
            assert vals[i] < vals[i + 1]

    def test_erfinv_known_values(self):
        """Check against known erfinv values within approximation tolerance."""
        # erfinv(0.5) ≈ 0.476936 (exact), Winitzki approx ~0.4769
        assert _erfinv(0.5) == pytest.approx(0.4769, rel=0.01)
        # erfinv(0.9) ≈ 1.163087
        assert _erfinv(0.9) == pytest.approx(1.1631, rel=0.01)


# ============================================================================
# compute_dsr tests
# ============================================================================

class TestComputeDSR:
    """Tests for the compute_dsr function."""

    # -- PSR degenerate case (N=1) ---------------------------------------

    def test_n1_equals_psr_strong(self):
        """N=1: DSR degenerates to PSR. Strong signal → high DSR."""
        dsr = compute_dsr(sharpe=2.0, t_stat=3.0, trial_count=1)
        # Engineer verified: 0.9987
        assert dsr == pytest.approx(0.9987, rel=1e-3)

    def test_n1_equals_psr_moderate(self):
        """N=1, moderate signal: SR=1.0, t=2.0."""
        dsr = compute_dsr(sharpe=1.0, t_stat=2.0, trial_count=1)
        # PSR = Φ(SR / SE) = Φ(SR * t_stat / SR) = Φ(t_stat) = Φ(2.0) ≈ 0.9772
        assert dsr == pytest.approx(0.9772, rel=0.01)

    def test_n1_equals_psr_weak(self):
        """N=1, weak signal: SR=0.5, t=1.0."""
        dsr = compute_dsr(sharpe=0.5, t_stat=1.0, trial_count=1)
        # PSR = Φ(1.0) ≈ 0.8413
        assert dsr == pytest.approx(0.8413, rel=0.01)

    def test_n1_borderline(self):
        """N=1, borderline: SR=0.1, t=0.5."""
        dsr = compute_dsr(sharpe=0.1, t_stat=0.5, trial_count=1)
        # PSR = Φ(0.5) ≈ 0.6915
        assert dsr == pytest.approx(0.6915, rel=0.02)

    # -- EVT correction (N>1) --------------------------------------------

    def test_n100_moderate_decay(self):
        """N=100 with moderate signal: DSR should be significantly lower."""
        dsr = compute_dsr(sharpe=2.0, t_stat=3.0, trial_count=100)
        # Engineer verified: 0.1966
        assert dsr == pytest.approx(0.1966, rel=0.02)

    def test_n1000_significant_decay(self):
        """N=1000: Even more deflation due to selection bias."""
        dsr_n1 = compute_dsr(sharpe=2.0, t_stat=3.0, trial_count=1)
        dsr_n1000 = compute_dsr(sharpe=2.0, t_stat=3.0, trial_count=1000)
        # DSR with many trials should be much lower than PSR
        assert dsr_n1000 < dsr_n1
        assert dsr_n1000 < 0.5  # Should be well below 0.5

    def test_n10_moderate(self):
        """N=10 moderate signal."""
        dsr = compute_dsr(sharpe=1.5, t_stat=2.5, trial_count=10)
        assert 0.0 < dsr < 1.0
        # Should be less than N=1 case
        dsr_n1 = compute_dsr(sharpe=1.5, t_stat=2.5, trial_count=1)
        assert dsr < dsr_n1

    def test_dsr_monotonic_decreasing_with_n(self):
        """DSR should be monotonically decreasing as trial_count increases."""
        sharpe, t_stat = 1.5, 2.5
        trials = [1, 2, 5, 10, 50, 100]
        values = [compute_dsr(sharpe, t_stat, n) for n in trials]
        for i in range(len(values) - 1):
            assert values[i] >= values[i + 1], (
                f"DSR not monotonic: N={trials[i]} → {values[i]:.4f}, "
                f"N={trials[i+1]} → {values[i+1]:.4f}"
            )

    # -- Zero / negative edge cases -------------------------------------

    def test_sharpe_zero(self):
        """sharpe=0 → DSR=0 regardless of other params."""
        assert compute_dsr(sharpe=0.0, t_stat=3.0, trial_count=1) == 0.0
        assert compute_dsr(sharpe=0.0, t_stat=3.0, trial_count=100) == 0.0

    def test_sharpe_negative(self):
        """Negative sharpe → DSR=0."""
        assert compute_dsr(sharpe=-1.0, t_stat=3.0, trial_count=1) == 0.0

    def test_t_stat_zero(self):
        """t_stat=0 → DSR=0."""
        assert compute_dsr(sharpe=2.0, t_stat=0.0, trial_count=1) == 0.0

    def test_t_stat_negative(self):
        """Negative t_stat → DSR=0."""
        assert compute_dsr(sharpe=2.0, t_stat=-1.0, trial_count=1) == 0.0

    def test_both_zero(self):
        """Both sharpe and t_stat zero → DSR=0."""
        assert compute_dsr(sharpe=0.0, t_stat=0.0, trial_count=1) == 0.0

    # -- Invalid trial_count --------------------------------------------

    def test_trial_count_zero_raises(self):
        """trial_count=0 → ValueError."""
        with pytest.raises(ValueError, match="trial_count must be >= 1"):
            compute_dsr(sharpe=1.0, t_stat=2.0, trial_count=0)

    def test_trial_count_negative_raises(self):
        """trial_count < 0 → ValueError."""
        with pytest.raises(ValueError, match="trial_count must be >= 1"):
            compute_dsr(sharpe=1.0, t_stat=2.0, trial_count=-5)

    # -- Very large trial_count -----------------------------------------

    def test_very_large_n(self):
        """Very large N (1M) should approach 0 but not crash."""
        dsr = compute_dsr(sharpe=2.0, t_stat=3.0, trial_count=1_000_000)
        assert 0.0 <= dsr <= 1.0
        # With 1M trials, DSR should be extremely small
        assert dsr < 0.01

    def test_large_n_no_overflow(self):
        """Large N should not cause numerical overflow."""
        for n in (10000, 100000, 1000000):
            dsr = compute_dsr(sharpe=1.0, t_stat=2.0, trial_count=n)
            assert 0.0 <= dsr <= 1.0

    # -- Output range ---------------------------------------------------

    def test_dsr_in_range(self):
        """DSR should always be in [0, 1]."""
        test_cases = [
            (2.0, 3.0, 1),
            (1.0, 2.0, 5),
            (0.5, 1.0, 10),
            (3.0, 4.0, 50),
            (0.1, 0.5, 100),
            (5.0, 6.0, 1000),
        ]
        for sharpe, t_stat, n in test_cases:
            dsr = compute_dsr(sharpe, t_stat, n)
            assert 0.0 <= dsr <= 1.0, (
                f"DSR out of range: {dsr} for SR={sharpe}, t={t_stat}, N={n}"
            )

    # -- Float return type ----------------------------------------------

    def test_returns_float(self):
        """compute_dsr should always return a float."""
        assert isinstance(compute_dsr(1.0, 2.0, 1), float)
        assert isinstance(compute_dsr(0.0, 3.0, 1), float)

    # -- Determinism ----------------------------------------------------

    def test_deterministic(self):
        """Same inputs → same output."""
        dsr1 = compute_dsr(1.5, 2.5, 10)
        dsr2 = compute_dsr(1.5, 2.5, 10)
        assert dsr1 == dsr2

    # -- DSR threshold interpretations ----------------------------------

    def test_strong_evidence_threshold(self):
        """SR=3.0, t=5.0, N=1 should give DSR > 0.95 (strong evidence)."""
        dsr = compute_dsr(sharpe=3.0, t_stat=5.0, trial_count=1)
        assert dsr > 0.95, f"Expected >0.95, got {dsr:.4f}"

    def test_moderate_evidence_threshold(self):
        """SR=1.5, t=3.0, N=2 should give DSR > 0.70 (moderate)."""
        dsr = compute_dsr(sharpe=1.5, t_stat=3.0, trial_count=2)
        assert dsr > 0.70, f"Expected >0.70, got {dsr:.4f}"

    def test_noise_level(self):
        """SR=0.5, t=0.8, N=100 should give DSR < 0.50 (noise)."""
        dsr = compute_dsr(sharpe=0.5, t_stat=0.8, trial_count=100)
        assert dsr < 0.50, f"Expected <0.50, got {dsr:.4f}"

    # -- Commented doc values cross-check --------------------------------

    def test_dsr_intermediate_n2(self):
        """N=2: one additional trial → slight deflation from PSR."""
        dsr_n1 = compute_dsr(sharpe=2.0, t_stat=3.0, trial_count=1)
        dsr_n2 = compute_dsr(sharpe=2.0, t_stat=3.0, trial_count=2)
        # N=2 should be slightly lower than N=1
        assert dsr_n2 < dsr_n1
        assert dsr_n2 > 0.9  # Still very high for strong signal with just 2 trials
