"""Package-local calibration wrapper for the research pipeline."""

from __future__ import annotations

from calibrate_weights import auto_calibrate_if_stalled

__all__ = ["auto_calibrate_if_stalled"]
