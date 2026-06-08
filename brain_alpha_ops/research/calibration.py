"""Package-local calibration wrapper for the research pipeline."""

from __future__ import annotations

def auto_calibrate_if_stalled(
    storage_dir: str = "data",
    **kwargs: object,
) -> dict:
    """Check convergence stats and auto-trigger calibration if stalled.

    Delegates to ``calibrate_weights.auto_calibrate_if_stalled`` when the
    standalone calibrator module is installed.  Returns a safe no-op result
    when it is not available so that the research pipeline is not blocked by
    a missing optional CLI dependency.
    """
    try:
        from calibrate_weights import auto_calibrate_if_stalled as _real  # type: ignore[import-not-found]

        return _real(storage_dir, **kwargs)
    except ImportError:
        return {"ok": True, "triggered": False, "reason": "calibrator_not_installed"}


__all__ = ["auto_calibrate_if_stalled"]
