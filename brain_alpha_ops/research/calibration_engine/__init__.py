"""Internal scoring-weight calibration helpers.

These helpers are consumed by the Web/automation pipeline after enough official
PASS/FAIL evidence has accumulated.  They are deliberately package-internal:
operators must use the browser Web console rather than a command-line tool.

This subpackage re-exports the public API previously exposed by the
monolithic ``calibration_engine.py`` module. External import paths are
unchanged::

    from brain_alpha_ops.research.calibration_engine import (
        load_alpha_features,
        compute_prior_dimensions,
        calibrate_prior_weights,
        calibrate_scorecard_weights,
        generate_mock_features,
        print_calibration_report,
        auto_calibrate_if_stalled,
    )
"""
from __future__ import annotations

from ._auto import auto_calibrate_if_stalled
from ._calibration import calibrate_prior_weights, calibrate_scorecard_weights
from ._data import compute_prior_dimensions, generate_mock_features, load_alpha_features
from ._report import print_calibration_report
from ._stats import _pearson_r, _predict_linear

__all__ = [
    "auto_calibrate_if_stalled",
    "calibrate_prior_weights",
    "calibrate_scorecard_weights",
    "compute_prior_dimensions",
    "generate_mock_features",
    "load_alpha_features",
    "print_calibration_report",
]
