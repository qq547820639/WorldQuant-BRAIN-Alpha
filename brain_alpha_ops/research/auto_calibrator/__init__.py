"""Auto-calibrator that learns from official backtest records.

It reads PASS records from data/alpha_features.jsonl, grid-searches parameters
for each scoring dimension, then uses calibrate_weights.py algorithms to
calibrate dimension weights and layer weights.

Trigger condition: enough new official_verified samples have accumulated.

Usage::

    from brain_alpha_ops.research.auto_calibrator import AutoCalibrator

        calibrator = AutoCalibrator(storage_dir="data")
        if calibrator.needs_calibration():
            report = calibrator.calibrate()
        # report["calibrated"] == True means calibration succeeded.

This subpackage re-exports the public API previously exposed by the
monolithic ``auto_calibrator.py`` module. External import paths are
unchanged::

    from brain_alpha_ops.research.auto_calibrator import AutoCalibrator
"""
from __future__ import annotations

import logging

from ._calibrator import AutoCalibrator

# Preserve the original logger name exactly as ``__name__`` would have
# produced in the monolithic module (``brain_alpha_ops.research.auto_calibrator``).
logger = logging.getLogger("brain_alpha_ops.research.auto_calibrator")

__all__ = ["AutoCalibrator"]
