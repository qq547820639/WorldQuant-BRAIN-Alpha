"""Weight-calibration helpers for ``AutoCalibrator``.

Extracted from the original ``auto_calibrator.py`` as a mixin so that the
dimension-weight and layer-weight calibration logic (which delegates to
``calibrate_weights.py``) remains cohesive while keeping the main
calibrator module small.
"""
from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.redaction import redact_error_message

# Preserve the original logger name exactly as ``__name__`` would have
# produced in the monolithic module.
logger = logging.getLogger("brain_alpha_ops.research.auto_calibrator")


class _WeightCalibrationMixin:
    """Provides dimension-weight and layer-weight calibration helpers."""

    def _calibrate_dimension_weights(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Calibrate 8-dimension weights with Pearson correlation.

        Data format is compatible with calibrate_weights.py:calibrate_prior_weights().
        """
        try:
            from calibrate_weights import calibrate_prior_weights

            return calibrate_prior_weights(records, target_metric="sharpe")
        except (ImportError, FileNotFoundError, AttributeError) as exc:
            logger.warning("calibrate_weights module not available for dimension weights: %s", redact_error_message(exc))
            return {
                "sample_size": len(records),
                "error": "calibrate_weights module not importable",
            }

    def _calibrate_layer_weights(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Calibrate three-layer weights with grid search.

        Data format is compatible with calibrate_weights.py:calibrate_scorecard_weights().
        """
        try:
            from calibrate_weights import calibrate_scorecard_weights

            return calibrate_scorecard_weights(records)
        except (ImportError, FileNotFoundError, AttributeError) as exc:
            logger.warning("calibrate_weights module not available for layer weights: %s", redact_error_message(exc))
            return {
                "sample_size": len(records),
                "error": "calibrate_weights module not importable",
            }
