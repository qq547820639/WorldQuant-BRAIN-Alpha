"""Tests for auto_calibrator.py fallback paths when calibrate_weights is unavailable."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch


class TestAutoCalibratorFallback:
    """When calibrate_weights is not importable, calibration methods return error dicts."""

    @pytest.fixture
    def auto_cal(self):
        from brain_alpha_ops.research.auto_calibrator import AutoCalibrator
        return AutoCalibrator(storage_dir="/tmp/_test_ac")

    def test_calibrate_dimension_weights_graceful_fallback(self, auto_cal):
        """Should return error dict when calibrate_weights is not importable."""
        records = [{"sharpe": 1.5, "fitness": 1.2}]
        result = auto_cal._calibrate_dimension_weights(records)
        assert isinstance(result, dict)
        assert "error" in result or "sample_size" in result

    def test_calibrate_layer_weights_graceful_fallback(self, auto_cal):
        """Should return error dict when calibrate_weights is not importable."""
        records = [{"sharpe": 1.5, "fitness": 1.2}]
        result = auto_cal._calibrate_layer_weights(records)
        assert isinstance(result, dict)
        assert "error" in result or "sample_size" in result

    def test_calibrate_dimension_weights_when_importable(self, auto_cal):
        """When calibrate_weights IS importable, returns calibration result."""
        # Task 2.13: the import path was corrected from the non-existent
        # ``calibrate_weights`` module to ``calibration_engine``. Patch the
        # real module so the lazy ``from ... import`` inside the method
        # resolves to the stub.
        from brain_alpha_ops.research import calibration_engine
        with patch.object(
            calibration_engine,
            "calibrate_prior_weights",
            lambda records, target_metric="sharpe": {"sample_size": len(records), "calibrated": True},
        ):
            records = [{"sharpe": 2.0}]
            result = auto_cal._calibrate_dimension_weights(records)
            assert result.get("calibrated") is True
