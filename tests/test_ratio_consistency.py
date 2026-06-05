"""Tests for _ratio normalization consistency across all modules.

Verifies that all _ratio() implementations across the codebase use the
same normalization heuristic (abs >= 2.0 → divide by 100), ensuring
consistent behavior for turnover, correlation, and other metrics.
"""

from __future__ import annotations

import pytest


class TestRatioConsistency:
    """Verify _ratio consistency across all implementations."""

    def test_experience_ratio_percentage_normalization(self):
        """experience.py:_ratio should normalize percentage-scale values."""
        from brain_alpha_ops.research.experience import _ratio

        # Percentage values (abs >= 2.0) should be divided by 100
        assert _ratio(75.0) == 0.75  # 75% → 0.75
        assert _ratio(150.0) == 1.50  # 150% → 1.50
        assert _ratio(-50.0) == -0.50  # -50% → -0.50

        # Decimal values (abs < 2.0) should pass through unchanged
        assert _ratio(0.75) == 0.75
        assert _ratio(1.5) == 1.50  # turnover can be 1.5 naturally
        assert _ratio(0.01) == 0.01
        assert _ratio(0.0) == 0.0

    def test_experience_ratio_non_numeric(self):
        """Non-numeric values should return 0.0."""
        from brain_alpha_ops.research.experience import _ratio

        assert _ratio(None) == 0.0
        assert _ratio("") == 0.0
        assert _ratio("abc") == 0.0

    def test_diagnostics_ratio_percentage_normalization(self):
        """diagnostics.py:_ratio should normalize percentage-scale values."""
        from brain_alpha_ops.research.diagnostics import _ratio

        # Percentage values
        assert _ratio(75.0) == 0.75
        assert _ratio(150.0) == 1.50

        # Decimal values pass through
        assert _ratio(0.75) == 0.75
        assert _ratio(1.5) == 1.50

    def test_safety_ratio_percentage_normalization(self):
        """safety.py:_ratio should normalize percentage-scale values."""
        from brain_alpha_ops.research.safety import _ratio

        # Percentage values
        assert _ratio(75.0) == 0.75
        assert _ratio(150.0) == 1.50

        # Decimal values pass through
        assert _ratio(0.75) == 0.75
        assert _ratio(1.5) == 1.50

    def test_scoring_ratio_bounded_mode(self):
        """scoring.py:_ratio with bounded=True should handle mid-range values."""
        from brain_alpha_ops.research.scoring import _ratio

        # Standard mode: only abs >= 100 triggers division
        assert _ratio(75.0) == 75.0  # not normalized (not >= 100)
        assert _ratio(150.0) == 1.50  # normalized (>= 100)

        # Bounded mode: also normalizes abs > 1.0
        assert _ratio(75.0, bounded=True) == 0.75  # bounded mode normalizes > 1.0
        assert _ratio(0.75, bounded=True) == 0.75  # already decimal
        assert _ratio(150.0, bounded=True) == 1.50  # both modes normalize >= 100

    def test_cross_module_consistency(self):
        """All _ratio implementations should agree on key cases."""
        from brain_alpha_ops.research.experience import _ratio as exp_ratio
        from brain_alpha_ops.research.diagnostics import _ratio as diag_ratio
        from brain_alpha_ops.research.safety import _ratio as safety_ratio

        # Case 1: turnover = 1.5 (natural decimal, should NOT be divided)
        assert exp_ratio(1.5) == 1.50
        assert diag_ratio(1.5) == 1.50
        assert safety_ratio(1.5) == 1.50

        # Case 2: turnover = 150% (percentage, should be divided)
        assert exp_ratio(150.0) == 1.50
        assert diag_ratio(150.0) == 1.50
        assert safety_ratio(150.0) == 1.50

        # Case 3: correlation = 0.70 (decimal, should pass through)
        assert exp_ratio(0.70) == 0.70
        assert diag_ratio(0.70) == 0.70
        assert safety_ratio(0.70) == 0.70

        # Case 4: concentration = 0.10 (decimal, pass through)
        assert exp_ratio(0.10) == 0.10
        assert diag_ratio(0.10) == 0.10
        assert safety_ratio(0.10) == 0.10

    def test_official_helpers_ratio(self):
        """official_helpers.py:_ratio uses the >= 2.0 heuristic."""
        from brain_alpha_ops.brain_api.official_helpers import _ratio as off_ratio

        # Percentage values (>= 2.0 → divide by 100)
        assert off_ratio(75.0) == 0.75
        assert off_ratio(150.0) == 1.50

        # The heuristic: >= 2.0 → divide by 100
        # turnover=3.5 → 3.5/100 = 0.035
        # This means turnover values in [2.0, 100) are treated as percentages.
        # This is a known trade-off documented in the code comments.
        result = off_ratio(3.5)
        assert result == 0.035  # abs >= 2.0 → normalized

        # Decimal values (< 2.0) pass through
        assert off_ratio(0.75) == 0.75
        assert off_ratio(1.5) == 1.5

    def test_turnover_boundary_values(self):
        """Test the boundary cases where normalization is ambiguous."""
        from brain_alpha_ops.research.experience import _ratio

        # Exactly at boundary: 2.0
        assert _ratio(2.0) == 0.02  # divided (abs >= 2.0)

        # Just below boundary: 1.999
        assert _ratio(1.999) == 1.999  # not divided (abs < 2.0)

        # Exactly at boundary: -2.0
        assert _ratio(-2.0) == -0.02  # divided (abs >= 2.0)

    def test_edge_case_zero(self):
        """Zero should pass through unchanged."""
        from brain_alpha_ops.research.experience import _ratio
        from brain_alpha_ops.research.diagnostics import _ratio as dr
        from brain_alpha_ops.research.safety import _ratio as sr

        assert _ratio(0.0) == 0.0
        assert dr(0.0) == 0.0
        assert sr(0.0) == 0.0
